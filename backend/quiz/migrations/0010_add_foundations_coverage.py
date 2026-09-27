from django.db import migrations


# Frozen additive content makes fresh and existing deployments converge.
QUESTIONS = [{'text': 'Which description best matches the lexis of a programming language?',
  'code_snippet': '',
  'difficulty': 'medium',
  'choices': [{'text': 'The rules for combining language elements into valid instructions.',
               'is_correct': False,
               'explanation': 'Wrong. Rules for combining elements describe syntax; lexis '
                              'identifies the language elements themselves.'},
              {'text': 'The vocabulary of words, symbols, and tokens recognized by the language.',
               'is_correct': True,
               'explanation': 'Correct. Lexis is the language vocabulary: the words, symbols, and '
                              'tokens from which valid instructions can be formed.'},
              {'text': 'The meaning and effect of every valid instruction.',
               'is_correct': False,
               'explanation': 'Wrong. Meaning and effect belong to semantics, not lexis.'},
              {'text': 'The speed at which the interpreter executes a program.',
               'is_correct': False,
               'explanation': 'Wrong. Execution performance is not part of a programming '
                              "language's lexis."}],
  'module': 'module1',
  'objective': '1.1'},
 {'text': 'Which assignment is rejected because its variable name is a Python keyword?',
  'code_snippet': '',
  'difficulty': 'medium',
  'choices': [{'text': 'class_name = 3',
               'is_correct': False,
               'explanation': 'Wrong. `class_name` is an ordinary identifier; containing the '
                              'letters in a keyword does not make the whole name reserved.'},
              {'text': 'Class = 3',
               'is_correct': False,
               'explanation': 'Wrong. Python identifiers are case-sensitive, so `Class` is '
                              'different from the lowercase keyword `class`.'},
              {'text': 'class = 3',
               'is_correct': True,
               'explanation': 'Correct. `class` is a reserved Python keyword and cannot be used as '
                              'a variable name.'},
              {'text': '_class = 3',
               'is_correct': False,
               'explanation': 'Wrong. `_class` is not the keyword `class`; the leading underscore '
                              'makes it a valid identifier.'}],
  'module': 'module1',
  'objective': '1.2'},
 {'text': 'What is an instruction in a Python program?',
  'code_snippet': '',
  'difficulty': 'medium',
  'choices': [{'text': 'Only a line that displays text on the screen.',
               'is_correct': False,
               'explanation': 'Wrong. Displaying output is one possible operation, but '
                              'instructions can assign values, make decisions, call functions, and '
                              'perform other operations.'},
              {'text': 'A command written according to the language rules that tells Python to '
                       'perform an operation.',
               'is_correct': True,
               'explanation': 'Correct. An instruction expresses an operation for Python to '
                              'execute and must follow the language syntax.'},
              {'text': 'Any text written after a `#` character.',
               'is_correct': False,
               'explanation': 'Wrong. Text after `#` is a comment and is ignored during '
                              'execution.'},
              {'text': 'A reserved keyword used without any surrounding code.',
               'is_correct': False,
               'explanation': 'Wrong. Keywords are vocabulary elements used to form instructions; '
                              'a keyword alone is not the definition of an instruction.'}],
  'module': 'module1',
  'objective': '1.2'}]


def add_foundations_coverage(apps, schema_editor):
    Question = apps.get_model('quiz', 'Question')
    Choice = apps.get_model('quiz', 'Choice')
    alias = schema_editor.connection.alias
    # Fresh databases are populated later by the idempotent seed command. Avoid
    # installing partial seed data during schema setup and test-database creation.
    if not Question.objects.using(alias).exists():
        return

    for source in QUESTIONS:
        rows = Question.objects.using(alias).filter(
            module=source['module'],
            text=source['text'],
            code_snippet=source['code_snippet'],
        )
        if rows.count() > 1:
            raise RuntimeError(f"Multiple questions match {source['text']!r}")
        question = rows.first()
        if question is None:
            question = Question.objects.using(alias).create(
                module=source['module'],
                objective=source['objective'],
                difficulty=source['difficulty'],
                text=source['text'],
                code_snippet=source['code_snippet'],
            )
            Choice.objects.using(alias).bulk_create(
                [
                    Choice(
                        question_id=question.id,
                        text=answer['text'],
                        is_correct=answer['is_correct'],
                        explanation=answer['explanation'],
                    )
                    for answer in source['choices']
                ]
            )
            continue

        actual_choices = list(
            question.choices.using(alias)
            .order_by('id')
            .values('text', 'is_correct', 'explanation')
        )
        if (
            question.objective != source['objective']
            or question.difficulty != source['difficulty']
            or actual_choices != source['choices']
        ):
            raise RuntimeError(
                f'Question id={question.id} differs from the reviewed source; '
                'refusing to overwrite it'
            )


class Migration(migrations.Migration):
    dependencies = [('quiz', '0009_replace_near_duplicate_questions')]
    operations = [
        migrations.RunPython(add_foundations_coverage, migrations.RunPython.noop)
    ]
