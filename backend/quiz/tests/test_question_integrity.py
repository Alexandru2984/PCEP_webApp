from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.forms.models import inlineformset_factory

from quiz.admin import ChoiceFormSet
from quiz.models import Question, Choice
from quiz.question_bank import (
    duplicate_questions,
    similar_questions,
    validation_errors,
)


def question(**overrides):
    return {'text': 'Question?', 'module': 'module1', 'difficulty': 'easy',
            'choices': [{'text': f'Option {i}', 'is_correct': i == 0,
                         'explanation': 'A meaningful explanation.'} for i in range(4)],
            **overrides}


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
