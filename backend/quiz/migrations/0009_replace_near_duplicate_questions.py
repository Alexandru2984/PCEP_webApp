from django.db import migrations
from django.utils import timezone


# Frozen question data keeps this migration deterministic after future bank edits.
REPLACEMENTS = [{'old': {'text': 'What does this print?',
          'code_snippet': "d = {'a': 1, 'b': 2}\nprint(d.get('c', 0))",
          'difficulty': 'easy',
          'choices': [{'text': '0',
                       'is_correct': True,
                       'explanation': 'Correct. `dict.get(key, default)` returns the default when '
                                      "the key is missing, so 'c' (absent) yields 0."},
                      {'text': 'KeyError',
                       'is_correct': False,
                       'explanation': 'Wrong. `get` never raises for a missing key; only `d[key]` '
                                      'does. That is the whole point of `get`.'},
                      {'text': 'None',
                       'is_correct': False,
                       'explanation': 'Wrong. `None` is the default only when you DO NOT supply '
                                      'one. Here the default is 0.'},
                      {'text': 'c',
                       'is_correct': False,
                       'explanation': 'Wrong. `get` returns the value or default, not the key.'}],
          'module': 'module3'},
  'new': {'text': 'What does this print?',
          'code_snippet': "settings = {'mode': 'dark'}\n"
                          "settings['size'] = 'large'\n"
                          "del settings['mode']\n"
                          'print(settings)',
          'difficulty': 'easy',
          'choices': [{'text': "{'size': 'large'}",
                       'is_correct': True,
                       'explanation': 'Correct. Assigning a new key adds `size`, and `del` then '
                                      'removes the existing `mode` key.'},
                      {'text': "{'mode': 'dark', 'size': 'large'}",
                       'is_correct': False,
                       'explanation': 'Wrong. This shows the dictionary before the `del '
                                      "settings['mode']` statement removes `mode`."},
                      {'text': "{'mode': 'large'}",
                       'is_correct': False,
                       'explanation': "Wrong. Assigning to `settings['size']` creates a separate "
                                      'key; it does not replace the value under `mode`.'},
                      {'text': 'KeyError',
                       'is_correct': False,
                       'explanation': 'Wrong. The `mode` key exists when `del` runs, so it is '
                                      'removed without an exception.'}],
          'module': 'module3'}},
 {'old': {'text': 'What is the output?',
          'code_snippet': 'a = [1, 2, 3]\nb = a\nb.append(4)\nprint(a)',
          'difficulty': 'medium',
          'choices': [{'text': '[1, 2, 3, 4]',
                       'is_correct': True,
                       'explanation': 'Correct. `b = a` binds the same list object, so appending '
                                      'via b is visible through a.'},
                      {'text': '[1, 2, 3]',
                       'is_correct': False,
                       'explanation': 'Wrong. `b = a` does not copy; both names refer to one '
                                      'list.'},
                      {'text': '[4, 1, 2, 3]',
                       'is_correct': False,
                       'explanation': 'Wrong. `append` adds to the end, but the key point is that '
                                      'a and b share the list.'},
                      {'text': '[1, 2, 3, [4]]',
                       'is_correct': False,
                       'explanation': 'Wrong. `append(4)` adds the integer 4, not a nested list.'}],
          'module': 'module3'},
  'new': {'text': 'What does this print?',
          'code_snippet': 'values = [10, 20, 30, 40]\ndel values[1:3]\nprint(values)',
          'difficulty': 'medium',
          'choices': [{'text': '[10, 40]',
                       'is_correct': True,
                       'explanation': 'Correct. The slice `1:3` covers indices 1 and 2, so `del` '
                                      'removes 20 and 30.'},
                      {'text': '[10, 30, 40]',
                       'is_correct': False,
                       'explanation': 'Wrong. A slice stop is exclusive, but `1:3` still includes '
                                      'both indices 1 and 2.'},
                      {'text': '[20, 30]',
                       'is_correct': False,
                       'explanation': 'Wrong. Those are the elements selected by the slice; `del` '
                                      'removes them and keeps the elements outside it.'},
                      {'text': 'TypeError',
                       'is_correct': False,
                       'explanation': 'Wrong. Deleting a valid slice from a list is permitted.'}],
          'module': 'module3'}}]


def _replace(apps, schema_editor, source, target):
    Question = apps.get_model('quiz', 'Question')
    alias = schema_editor.connection.alias
    source_rows = Question.objects.using(alias).filter(
        module=source['module'],
        text=source['text'],
        code_snippet=source['code_snippet'],
    )
    if source_rows.count() > 1:
        raise RuntimeError(f"Multiple questions match {source['text']!r}")
    question = source_rows.first()
    if question is None:
        return

    choices = list(question.choices.using(alias).order_by('id'))
    actual_choices = [
        {
            'text': answer.text,
            'is_correct': answer.is_correct,
            'explanation': answer.explanation,
        }
        for answer in choices
    ]
    if (
        len(choices) != len(target['choices'])
        or question.difficulty != source['difficulty']
        or actual_choices != source['choices']
    ):
        raise RuntimeError(
            f'Question id={question.id} differs from the reviewed source; '
            'refusing to overwrite it'
        )

    question.text = target['text']
    question.code_snippet = target['code_snippet']
    question.difficulty = target['difficulty']
    question.updated_at = timezone.now()
    question.save(
        using=alias,
        update_fields=['text', 'code_snippet', 'difficulty', 'updated_at'],
    )
    for answer, replacement in zip(choices, target['choices'], strict=True):
        answer.text = replacement['text']
        answer.is_correct = replacement['is_correct']
        answer.explanation = replacement['explanation']
        answer.save(
            using=alias,
            update_fields=['text', 'is_correct', 'explanation'],
        )


def replace_near_duplicates(apps, schema_editor):
    for replacement in REPLACEMENTS:
        _replace(apps, schema_editor, replacement['old'], replacement['new'])


def restore_near_duplicates(apps, schema_editor):
    for replacement in REPLACEMENTS:
        _replace(apps, schema_editor, replacement['new'], replacement['old'])


class Migration(migrations.Migration):
    dependencies = [('quiz', '0008_replace_out_of_scope_constructs')]
    operations = [
        migrations.RunPython(replace_near_duplicates, restore_near_duplicates)
    ]
