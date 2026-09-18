from django.db import migrations


SNIPPET = 'print(0 or "" or "x" or "y")'


def label_empty_output(apps, schema_editor):
    Choice = apps.get_model('quiz', 'Choice')
    Choice.objects.using(schema_editor.connection.alias).filter(
        question__module='module2', question__code_snippet=SNIPPET,
        text='', is_correct=False,
    ).update(text='(empty output)')


def restore_empty_output(apps, schema_editor):
    Choice = apps.get_model('quiz', 'Choice')
    Choice.objects.using(schema_editor.connection.alias).filter(
        question__module='module2', question__code_snippet=SNIPPET,
        text='(empty output)', is_correct=False,
    ).update(text='')


class Migration(migrations.Migration):
    dependencies = [('quiz', '0002_question_module')]
    operations = [migrations.RunPython(label_empty_output, restore_empty_output)]
