from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.forms.models import inlineformset_factory

from quiz.admin import ChoiceFormSet
from quiz.models import Question, Choice
from quiz.question_bank import (
    duplicate_questions,
    similar_questions,
    syllabus_warnings,
    validation_errors,
)
from quiz.syllabus import OBJECTIVES_BY_MODULE


def question(**overrides):
    result = {
        'text': 'Question?',
        'module': 'module1',
        'difficulty': 'easy',
        'choices': [
            {
                'text': f'Option {i}',
                'is_correct': i == 0,
                'explanation': 'A meaningful explanation.',
            }
            for i in range(4)
        ],
        **overrides,
    }
    result.setdefault('objective', OBJECTIVES_BY_MODULE[result['module']][0])
    return result


def test_validation_reports_empty_and_duplicate_options():
    q = question(text=' ')
    q['choices'][1]['text'] = q['choices'][0]['text']
    q['choices'][2]['text'] = ' '
    q['choices'][3]['explanation'] = ' '
    errors = ' '.join(validation_errors([q]))
    assert all(term in errors for term in ('empty question', 'duplicate option',
                                           'empty text', 'empty explanation'))


def test_python_option_case_is_semantically_significant():
    q = question()
    q['choices'][0]['text'] = 'True'
    q['choices'][1]['text'] = 'true'
    assert not validation_errors([q])


def test_duplicate_audit_ignores_python_quote_and_whitespace_style():
    first = question(text='What is the output?', code_snippet='print("same")')
    second = question(text='  What  is the output? ', code_snippet="print( 'same' )")
    assert [index for index, _ in duplicate_questions([first, second])] == [1, 2]
    assert similar_questions([first, second]) == []


def test_near_duplicate_audit_returns_distinct_high_similarity_candidates():
    first = question(
        module='module3',
        text='What is the output?',
        code_snippet='print([x for x in range(4) if x])',
    )
    second = question(
        module='module3',
        text='What is the output?',
        code_snippet='print([x for x in range(4) if x > 0])',
    )
    [(first_index, second_index, similarity, _, _)] = similar_questions(
        [first, second], threshold=0.8
    )
    assert (first_index, second_index) == (1, 2)
    assert similarity >= 0.8


@pytest.mark.parametrize(
    'snippet',
    [
        'items = {1, 2, 3}',
        'items = {value for value in range(3)}',
        'items = set([1, 2, 3])',
    ],
)
def test_syllabus_audit_reports_set_usage(snippet):
    warnings = syllabus_warnings([question(module='module3', code_snippet=snippet)])
    assert warnings == [
        'question #1 uses sets, which are outside the PCEP-30-02 data-collection objectives'
    ]


@pytest.mark.parametrize(
    ('snippet', 'expected'),
    [
        ('square = lambda value: value * value', 'lambda expressions'),
        ('def inner():\n    nonlocal value', '`nonlocal`'),
        ('assert value > 0', '`assert`/`AssertionError`'),
        ('number = 2j', 'complex literals'),
        ('mapping = {value: value for value in range(3)}', 'dictionary comprehensions'),
        ('first, *rest = [1, 2, 3]', 'starred unpacking'),
        ("message = f'value={value}'", 'f-strings'),
        ("pairs = enumerate('ab')", '`enumerate()`'),
        ('name = type(1).__name__', '`__name__` introspection'),
    ],
)
def test_syllabus_audit_reports_unlisted_language_features(snippet, expected):
    warnings = syllabus_warnings([question(code_snippet=snippet)])
    assert len(warnings) == 1
    assert expected in warnings[0]


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('Does this lambda return a value?', 'lambda expressions'),
        ('What does nonlocal change?', '`nonlocal`'),
        ('Does assert raise AssertionError?', '`assert`/`AssertionError`'),
        ('Is this a complex number?', 'complex numbers'),
        ('Is this a dictionary comprehension?', 'dictionary comprehensions'),
        ('Does starred unpacking create a list?', 'starred unpacking'),
        ('Does this f-string interpolate?', 'f-strings'),
        ('What does enumerate() produce?', '`enumerate()`'),
        ('What is the value of __name__?', '`__name__` introspection'),
    ],
)
def test_syllabus_audit_reports_unlisted_features_in_explanatory_text(text, expected):
    warnings = syllabus_warnings([question(text=text)])
    assert len(warnings) == 1
    assert expected in warnings[0]


def test_validation_rejects_missing_or_cross_module_objectives():
    missing = question()
    missing.pop('objective')
    mismatched = question(module='module3', objective='2.1')
    errors = ' '.join(validation_errors([missing, mismatched]))
    assert 'invalid objective' in errors
    assert 'does not belong to' in errors


@pytest.mark.django_db
def test_database_rejects_an_objective_from_another_module(make_question):
    q = make_question(module='module1', objective='1.4')
    with pytest.raises(IntegrityError), transaction.atomic():
        Question.objects.filter(id=q.id).update(objective='3.1')


@pytest.mark.django_db
@pytest.mark.parametrize('correct_count', [0, 1, 2])
def test_admin_inline_requires_one_correct_answer(make_question, correct_count):
    q = make_question()
    cls = inlineformset_factory(Question, Choice, formset=ChoiceFormSet,
                               fields=('text', 'is_correct', 'explanation'), extra=0)
    data = {'choices-TOTAL_FORMS': '4', 'choices-INITIAL_FORMS': '4',
            'choices-MIN_NUM_FORMS': '0', 'choices-MAX_NUM_FORMS': '1000'}
    for i, choice in enumerate(q.choices.all()):
        data.update({f'choices-{i}-id': choice.id, f'choices-{i}-question': q.id,
                     f'choices-{i}-text': choice.text,
                     f'choices-{i}-explanation': choice.explanation})
        if i < correct_count:
            data[f'choices-{i}-is_correct'] = 'on'
    formset = cls(data=data, instance=q, prefix='choices')
    assert formset.is_valid() is (correct_count == 1)
    if correct_count != 1:
        assert 'exactly one' in str(formset.non_form_errors())


@pytest.mark.django_db
def test_database_audit_detects_actual_answer_key_errors(make_question):
    q = make_question()
    q.choices.update(is_correct=False)
    out = StringIO()
    with pytest.raises(CommandError, match='data errors'):
        call_command('audit_questions', database=True, stdout=out)
    assert f'database question id={q.id}' in out.getvalue()
    assert '0 correct choices' in out.getvalue()


@pytest.mark.django_db
def test_invalid_seed_is_rejected_before_reset(make_question):
    q = make_question()
    with patch('quiz.management.commands.seed_questions.ALL_QUESTIONS', [question(text='')]):
        with pytest.raises(CommandError, match='Refusing invalid seed'):
            call_command('seed_questions', reset=True)
    assert Question.objects.filter(id=q.id).exists()


@pytest.mark.django_db
def test_empty_output_migration_preserves_question_and_choice_ids(make_question):
    import importlib
    from django.apps import apps
    from django.db import connection
    migration = importlib.import_module('quiz.migrations.0003_label_empty_output_choice')
    q = make_question(module='module2')
    q.code_snippet = migration.SNIPPET
    q.save()
    choice = q.choices.filter(is_correct=False).first()
    choice.text = ''
    choice.save()
    editor = connection.schema_editor()
    migration.label_empty_output(apps, editor)
    choice.refresh_from_db()
    assert choice.text == '(empty output)'
    assert choice.question_id == q.id
    migration.restore_empty_output(apps, editor)
    choice.refresh_from_db()
    assert choice.text == ''


@pytest.mark.django_db
def test_duplicate_replacement_migration_preserves_all_ids(make_question):
    import importlib
    from django.apps import apps
    from django.db import connection
    migration = importlib.import_module(
        'quiz.migrations.0004_replace_duplicate_exception_question'
    )
    q = make_question(module='module4', difficulty='easy')
    q.text = migration.QUESTION_TEXT
    q.code_snippet = migration.OLD_SNIPPET
    q.save()
    choice_ids = list(q.choices.values_list('id', flat=True))
    editor = connection.schema_editor()

    migration.replace_duplicate(apps, editor)
    q.refresh_from_db()
    assert q.code_snippet == migration.NEW_SNIPPET
    assert list(q.choices.values_list('id', flat=True)) == choice_ids
    assert q.choices.get(is_correct=True).text == '4'

    migration.restore_duplicate(apps, editor)
    q.refresh_from_db()
    assert q.code_snippet == migration.OLD_SNIPPET
    assert list(q.choices.values_list('id', flat=True)) == choice_ids


@pytest.mark.django_db
def test_comprehension_replacement_migration_preserves_all_ids(make_question):
    import importlib
    from django.apps import apps
    from django.db import connection
    migration = importlib.import_module(
        'quiz.migrations.0005_replace_equivalent_comprehension'
    )
    q = make_question(module='module3', difficulty='hard')
    q.text = migration.QUESTION_TEXT
    q.code_snippet = migration.OLD_SNIPPET
    q.save()
    choice_ids = list(q.choices.values_list('id', flat=True))
    editor = connection.schema_editor()

    migration.replace_equivalent(apps, editor)
    q.refresh_from_db()
    assert q.code_snippet == migration.NEW_SNIPPET
    assert list(q.choices.values_list('id', flat=True)) == choice_ids
    assert q.choices.get(is_correct=True).text == '[4]'

    migration.restore_equivalent(apps, editor)
    q.refresh_from_db()
    assert q.code_snippet == migration.OLD_SNIPPET
    assert list(q.choices.values_list('id', flat=True)) == choice_ids
    assert q.choices.get(is_correct=True).text == '[2, 6]'


@pytest.mark.django_db
def test_set_replacement_migration_preserves_all_ids(make_question):
    import importlib
    from django.apps import apps
    from django.db import connection
    migration = importlib.import_module(
        'quiz.migrations.0006_replace_out_of_syllabus_sets'
    )
    editor = connection.schema_editor()
    questions = []
    original_choice_ids = []
    for replacement in migration.REPLACEMENTS:
        source = replacement['old']
        q = make_question(module='module3', difficulty=source['difficulty'])
        q.text = source['text']
        q.code_snippet = source['code_snippet']
        q.save()
        questions.append(q)
        original_choice_ids.append(list(q.choices.values_list('id', flat=True)))

    migration.replace_out_of_syllabus_sets(apps, editor)
    for q, choice_ids, replacement in zip(
        questions, original_choice_ids, migration.REPLACEMENTS, strict=True
    ):
        q.refresh_from_db()
        assert q.code_snippet == replacement['new']['code_snippet']
        assert list(q.choices.values_list('id', flat=True)) == choice_ids
        assert q.choices.get(is_correct=True).text == replacement['new']['choices'][0][0]

    migration.restore_out_of_syllabus_sets(apps, editor)
    for q, choice_ids, replacement in zip(
        questions, original_choice_ids, migration.REPLACEMENTS, strict=True
    ):
        q.refresh_from_db()
        assert q.code_snippet == replacement['old']['code_snippet']
        assert list(q.choices.values_list('id', flat=True)) == choice_ids


@pytest.mark.django_db
def test_scope_replacement_migration_preserves_question_and_choice_ids(make_question):
    import importlib
    from django.apps import apps
    from django.db import connection

    migration = importlib.import_module(
        'quiz.migrations.0008_replace_out_of_scope_constructs'
    )
    questions = []
    original_choice_ids = []
    for replacement in migration.REPLACEMENTS:
        source = replacement['old']
        target = replacement['new']
        source_correct = [
            index for index, answer in enumerate(source['choices'])
            if answer['is_correct']
        ]
        target_correct = [
            index for index, answer in enumerate(target['choices'])
            if answer['is_correct']
        ]
        assert source_correct == target_correct

        q = make_question(module=source['module'], difficulty=source['difficulty'])
        q.text = source['text']
        q.code_snippet = source['code_snippet']
        q.save()
        for answer, expected in zip(
            q.choices.order_by('id'), source['choices'], strict=True
        ):
            answer.text = expected['text']
            answer.is_correct = expected['is_correct']
            answer.explanation = expected['explanation']
            answer.save(update_fields=['text', 'is_correct', 'explanation'])
        questions.append(q)
        original_choice_ids.append(list(q.choices.values_list('id', flat=True)))

    editor = connection.schema_editor()
    migration.replace_out_of_scope_constructs(apps, editor)
    for q, choice_ids, replacement in zip(
        questions, original_choice_ids, migration.REPLACEMENTS, strict=True
    ):
        q.refresh_from_db()
        assert q.text == replacement['new']['text']
        assert q.code_snippet == replacement['new']['code_snippet']
        assert list(q.choices.values_list('id', flat=True)) == choice_ids
        assert q.choices.get(is_correct=True).text == next(
            answer['text']
            for answer in replacement['new']['choices']
            if answer['is_correct']
        )

    migration.restore_out_of_scope_constructs(apps, editor)
    for q, choice_ids, replacement in zip(
        questions, original_choice_ids, migration.REPLACEMENTS, strict=True
    ):
        q.refresh_from_db()
        assert q.text == replacement['old']['text']
        assert q.code_snippet == replacement['old']['code_snippet']
        assert list(q.choices.values_list('id', flat=True)) == choice_ids


@pytest.mark.django_db
def test_scope_replacement_refuses_unreviewed_database_edits(make_question):
    import importlib
    from django.apps import apps
    from django.db import connection

    migration = importlib.import_module(
        'quiz.migrations.0008_replace_out_of_scope_constructs'
    )
    source = migration.REPLACEMENTS[0]['old']
    q = make_question(module=source['module'], difficulty=source['difficulty'])
    q.text = source['text']
    q.code_snippet = source['code_snippet']
    q.save()
    for answer, expected in zip(
        q.choices.order_by('id'), source['choices'], strict=True
    ):
        answer.text = expected['text']
        answer.is_correct = expected['is_correct']
        answer.explanation = expected['explanation']
        answer.save(update_fields=['text', 'is_correct', 'explanation'])
    first_choice = q.choices.order_by('id').first()
    first_choice.explanation = 'A production-only edit.'
    first_choice.save(update_fields=['explanation'])

    with pytest.raises(RuntimeError, match='refusing to overwrite'):
        migration.replace_out_of_scope_constructs(apps, connection.schema_editor())


@pytest.mark.django_db
def test_near_duplicate_replacement_preserves_all_ids(make_question):
    import importlib
    from django.apps import apps
    from django.db import connection

    migration = importlib.import_module(
        'quiz.migrations.0009_replace_near_duplicate_questions'
    )
    questions = []
    choice_ids = []
    for replacement in migration.REPLACEMENTS:
        source = replacement['old']
        target = replacement['new']
        assert [a['is_correct'] for a in source['choices']] == [
            a['is_correct'] for a in target['choices']
        ]
        q = make_question(module=source['module'], difficulty=source['difficulty'])
        q.text = source['text']
        q.code_snippet = source['code_snippet']
        q.save()
        for answer, expected in zip(
            q.choices.order_by('id'), source['choices'], strict=True
        ):
            answer.text = expected['text']
            answer.is_correct = expected['is_correct']
            answer.explanation = expected['explanation']
            answer.save(update_fields=['text', 'is_correct', 'explanation'])
        questions.append(q)
        choice_ids.append(list(q.choices.values_list('id', flat=True)))

    editor = connection.schema_editor()
    migration.replace_near_duplicates(apps, editor)
    for q, ids, replacement in zip(
        questions, choice_ids, migration.REPLACEMENTS, strict=True
    ):
        q.refresh_from_db()
        assert q.code_snippet == replacement['new']['code_snippet']
        assert list(q.choices.values_list('id', flat=True)) == ids

    migration.restore_near_duplicates(apps, editor)
    for q, ids, replacement in zip(
        questions, choice_ids, migration.REPLACEMENTS, strict=True
    ):
        q.refresh_from_db()
        assert q.code_snippet == replacement['old']['code_snippet']
        assert list(q.choices.values_list('id', flat=True)) == ids


@pytest.mark.django_db
def test_objective_migration_assigns_frozen_taxonomy(make_question):
    import importlib
    from django.apps import apps
    from django.db import connection
    from quiz.seed_data import ALL_QUESTIONS

    migration = importlib.import_module('quiz.migrations.0007_add_question_objective')
    source = ALL_QUESTIONS[0]
    q = make_question(
        module=source['module'],
        difficulty=source['difficulty'],
        text=source['text'],
        code_snippet=source['code_snippet'],
        objective='1.1',
    )

    migration.assign_objectives(apps, connection.schema_editor())

    q.refresh_from_db()
    assert q.objective == source['objective']


def test_migration_chain_covers_the_complete_reviewed_bank():
    import importlib
    from types import SimpleNamespace
    from quiz.seed_data import ALL_QUESTIONS

    objective_migration = importlib.import_module(
        'quiz.migrations.0007_add_question_objective'
    )
    objective_by_signature = dict(objective_migration.OBJECTIVE_BY_SIGNATURE)
    for migration_name in (
        'quiz.migrations.0008_replace_out_of_scope_constructs',
        'quiz.migrations.0009_replace_near_duplicate_questions',
    ):
        content_migration = importlib.import_module(migration_name)
        for replacement in content_migration.REPLACEMENTS:
            old = SimpleNamespace(**replacement['old'])
            new = SimpleNamespace(**replacement['new'])
            objective_by_signature[objective_migration._signature(new)] = (
                objective_by_signature[objective_migration._signature(old)]
            )

    signatures = []
    for source in ALL_QUESTIONS:
        question = SimpleNamespace(
            module=source['module'],
            text=source['text'],
            code_snippet=source.get('code_snippet', ''),
        )
        signature = objective_migration._signature(question)
        signatures.append(signature)
        assert objective_by_signature[signature] == source['objective']
    assert len(signatures) == len(set(signatures)) == len(ALL_QUESTIONS)


@pytest.mark.django_db
def test_objective_migration_refuses_an_unreviewed_question(make_question):
    import importlib
    from django.apps import apps
    from django.db import connection

    migration = importlib.import_module('quiz.migrations.0007_add_question_objective')
    q = make_question(text='An unreviewed production-only question?')

    with pytest.raises(RuntimeError, match=str(q.id)):
        migration.assign_objectives(apps, connection.schema_editor())
