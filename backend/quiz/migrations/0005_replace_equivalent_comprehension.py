from django.db import migrations
from django.utils import timezone


QUESTION_TEXT = 'What is the output?'
OLD_SNIPPET = 'print([x * 2 for x in range(4) if x % 2])'
NEW_SNIPPET = 'print([x for x in range(6) if x % 2 == 0 if x > 2])'
OLD_CHOICES = [
    ('[2, 6]', True, 'Correct. `if x % 2` keeps odd x (1 and 3); doubling gives 2 and 6.'),
    ('[0, 2, 4, 6]', False, 'Wrong. The `if x % 2` filter drops even x (0 and 2) before doubling.'),
    ('[2, 4, 6]', False, 'Wrong. Only odd x survive the filter: x = 1 and x = 3.'),
    ('[1, 3]', False, 'Wrong. Those are the surviving x values before the `* 2` is applied.'),
]
NEW_CHOICES = [
    ('[4]', True, 'Correct. Both filters must pass: from 0 through 5, the even values are 0, 2 and 4, and only 4 is greater than 2.'),
    ('[0, 2, 4]', False, 'Wrong. These values pass the even-number filter, but 0 and 2 fail the second condition `x > 2`.'),
    ('[3, 4, 5]', False, 'Wrong. These values satisfy `x > 2`, but 3 and 5 fail the even-number condition.'),
    ('[]', False, 'Wrong. The value 4 satisfies both conditions, so the resulting list is not empty.'),
]


def _replace(apps, schema_editor, source, target, choices):
    Question = apps.get_model('quiz', 'Question')
    alias = schema_editor.connection.alias
    question = (
        Question.objects.using(alias)
        .filter(module='module3', text=QUESTION_TEXT, code_snippet=source)
        .order_by('id')
        .first()
    )
    if question is None:
        return
    existing_choices = list(question.choices.using(alias).order_by('id'))
    if len(existing_choices) != len(choices):
        return

    question.code_snippet = target
    question.difficulty = 'hard'
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


def replace_equivalent(apps, schema_editor):
    _replace(apps, schema_editor, OLD_SNIPPET, NEW_SNIPPET, NEW_CHOICES)


def restore_equivalent(apps, schema_editor):
    _replace(apps, schema_editor, NEW_SNIPPET, OLD_SNIPPET, OLD_CHOICES)


class Migration(migrations.Migration):
    dependencies = [('quiz', '0004_replace_duplicate_exception_question')]
    operations = [migrations.RunPython(replace_equivalent, restore_equivalent)]
