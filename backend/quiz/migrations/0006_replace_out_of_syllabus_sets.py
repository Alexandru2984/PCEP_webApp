from django.db import migrations
from django.utils import timezone


REPLACEMENTS = [
    {
        'old': {
            'text': 'What is the length?',
            'code_snippet': 'print(len({1, 2, 2, 3, 3, 3}))',
            'difficulty': 'easy',
            'choices': [
                ('3', True, 'Correct. A set stores only UNIQUE values, so duplicates collapse to {1, 2, 3} — length 3.'),
                ('6', False, 'Wrong. Sets discard duplicates; the literal has only three distinct values.'),
                ('1', False, 'Wrong. There are three distinct values, not one.'),
                ('2', False, 'Wrong. The distinct values are 1, 2 and 3 — three of them.'),
            ],
        },
        'new': {
            'text': 'What does this print?',
            'code_snippet': "d = {'a': 1, 'b': 2}\nprint(list(d.values()))",
            'difficulty': 'easy',
            'choices': [
                ('[1, 2]', True, 'Correct. `values()` exposes the dictionary values in insertion order, and `list()` converts that view to `[1, 2]`.'),
                ("['a', 'b']", False, 'Wrong. Those are the dictionary keys. `d.keys()` would expose them; `d.values()` exposes 1 and 2.'),
                ('dict_values([1, 2])', False, 'Wrong. `d.values()` is a view, but the surrounding `list(...)` converts it to a regular list before printing.'),
                ('(1, 2)', False, 'Wrong. `list()` creates a list with square brackets, not a tuple with parentheses.'),
            ],
        },
    },
    {
        'old': {
            'text': 'What is the output?',
            'code_snippet': 'print(len({1, 2, 2, 3, 3, 3}))',
            'difficulty': 'hard',
            'choices': [
                ('3', True, 'Correct. A set stores only distinct values, so duplicates collapse to {1, 2, 3} with length 3.'),
                ('6', False, 'Wrong. Sets discard duplicates; the six literals reduce to three unique elements.'),
                ('1', False, 'Wrong. There are three distinct values, not one.'),
                ('4', False, 'Wrong. The unique values are exactly 1, 2, 3.'),
            ],
        },
        'new': {
            'text': 'What is the output?',
            'code_snippet': "d = {'x': 1, 'y': 2}\nitems = d.items()\nd['x'] = 9\nprint(list(items))",
            'difficulty': 'hard',
            'choices': [
                ("[('x', 9), ('y', 2)]", True, 'Correct. `items` is a dynamic dictionary view. Updating the value for `x` is visible when the view is later converted to a list.'),
                ("[('x', 1), ('y', 2)]", False, 'Wrong. `dict.items()` does not take a frozen snapshot; its view reflects the later value update.'),
                ("[('x', 1), ('y', 2), ('x', 9)]", False, 'Wrong. Assigning to an existing key replaces its value; dictionaries cannot contain the same key twice.'),
                ('RuntimeError', False, 'Wrong. The dictionary size does not change, and reading the view after a value update is valid.'),
            ],
        },
    },
]


def _replace(apps, schema_editor, source, target):
    Question = apps.get_model('quiz', 'Question')
    alias = schema_editor.connection.alias
    question = (
        Question.objects.using(alias)
        .filter(
            module='module3',
            text=source['text'],
            code_snippet=source['code_snippet'],
        )
        .order_by('id')
        .first()
    )
    if question is None:
        return
    choices = list(question.choices.using(alias).order_by('id'))
    if len(choices) != len(target['choices']):
        return

    question.text = target['text']
    question.code_snippet = target['code_snippet']
    question.difficulty = target['difficulty']
    question.updated_at = timezone.now()
    question.save(
        using=alias,
        update_fields=['text', 'code_snippet', 'difficulty', 'updated_at'],
    )
    for choice, (text, is_correct, explanation) in zip(
        choices, target['choices'], strict=True
    ):
        choice.text = text
        choice.is_correct = is_correct
        choice.explanation = explanation
        choice.save(
            using=alias,
            update_fields=['text', 'is_correct', 'explanation'],
        )


def replace_out_of_syllabus_sets(apps, schema_editor):
    for replacement in REPLACEMENTS:
        _replace(apps, schema_editor, replacement['old'], replacement['new'])


def restore_out_of_syllabus_sets(apps, schema_editor):
    for replacement in REPLACEMENTS:
        _replace(apps, schema_editor, replacement['new'], replacement['old'])


class Migration(migrations.Migration):
    dependencies = [('quiz', '0005_replace_equivalent_comprehension')]
    operations = [
        migrations.RunPython(
            replace_out_of_syllabus_sets,
            restore_out_of_syllabus_sets,
        )
    ]
