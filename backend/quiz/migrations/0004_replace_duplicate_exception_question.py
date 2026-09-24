from django.db import migrations
from django.utils import timezone


QUESTION_TEXT = 'What is the output?'
OLD_SNIPPET = 'try:\n    print(1 / 0)\nexcept ZeroDivisionError:\n    print(\'zero\')'
NEW_SNIPPET = (
    'try:\n'
    '    value = 8 // 2\n'
    'except ZeroDivisionError:\n'
    "    print('error')\n"
    'else:\n'
    '    print(value)'
)
OLD_CHOICES = [
    ('zero', True, 'Correct. `1 / 0` raises ZeroDivisionError, which the except clause catches and handles.'),
    ('0', False, 'Wrong. Division by zero raises rather than producing 0.'),
    ('ZeroDivisionError', False, "Wrong. The exception is caught, so the traceback is not shown; 'zero' is printed."),
    ('1', False, 'Wrong. The division never completes; control jumps to the except block.'),
]
NEW_CHOICES = [
    ('4', True, 'Correct. `8 // 2` evaluates to 4 without raising. The `except` block is skipped and the `else` block prints `value`.'),
    ('error', False, 'Wrong. `8 // 2` is valid integer floor division, so no `ZeroDivisionError` is raised and the handler does not run.'),
    ('4\\nerror', False, 'Wrong. A `try` statement runs either the matching exception handler or its `else` block here, not both.'),
    ('ZeroDivisionError', False, 'Wrong. The divisor is 2, so the calculation succeeds and no exception is raised.'),
]


def _replace(apps, schema_editor, source, target, choices):
    Question = apps.get_model('quiz', 'Question')
    alias = schema_editor.connection.alias
    question = (
        Question.objects.using(alias)
        .filter(module='module4', text=QUESTION_TEXT, code_snippet=source)
        .order_by('id')
        .first()
    )
    if question is None:
        return
    existing_choices = list(question.choices.using(alias).order_by('id'))
    if len(existing_choices) != len(choices):
        return

    question.code_snippet = target
    question.difficulty = 'easy'
    question.updated_at = timezone.now()
    question.save(
        using=alias,
        update_fields=['code_snippet', 'difficulty', 'updated_at'],
    )
    for choice, (text, is_correct, explanation) in zip(
        existing_choices, choices, strict=True
    ):
        choice.text = text
        choice.is_correct = is_correct
        choice.explanation = explanation
        choice.save(
            using=alias,
            update_fields=['text', 'is_correct', 'explanation'],
        )


def replace_duplicate(apps, schema_editor):
    _replace(apps, schema_editor, OLD_SNIPPET, NEW_SNIPPET, NEW_CHOICES)


def restore_duplicate(apps, schema_editor):
    _replace(apps, schema_editor, NEW_SNIPPET, OLD_SNIPPET, OLD_CHOICES)


class Migration(migrations.Migration):
    dependencies = [('quiz', '0003_label_empty_output_choice')]
    operations = [migrations.RunPython(replace_duplicate, restore_duplicate)]
