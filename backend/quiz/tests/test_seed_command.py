from io import StringIO

import pytest
from django.core.management import call_command

from quiz.models import Question
from quiz.seed_data import ALL_QUESTIONS


pytestmark = pytest.mark.django_db


def run_seed(*args):
    out = StringIO()
    call_command('seed_questions', *args, stdout=out)
    return out.getvalue()


def test_seed_questions_is_idempotent_by_default():
    first = run_seed()
    assert Question.objects.count() == len(ALL_QUESTIONS)
    assert f'created={len(ALL_QUESTIONS)}' in first

    second = run_seed()
    assert Question.objects.count() == len(ALL_QUESTIONS)
    assert 'created=0' in second
    assert f'skipped={len(ALL_QUESTIONS)}' in second


def test_seed_questions_update_refreshes_existing_choices():
    run_seed()
    question = Question.objects.first()
    question.difficulty = Question.DIFFICULTY_EASY
    question.save(update_fields=['difficulty'])
    question.choices.all().delete()

    out = run_seed('--update')

    question.refresh_from_db()
    assert question.choices.count() == 4
    assert f'updated={len(ALL_QUESTIONS)}' in out


def test_seed_questions_dry_run_does_not_write():
    out = run_seed('--dry-run')

    assert Question.objects.count() == 0
    assert 'Dry run' in out
    assert f'Would create {len(ALL_QUESTIONS)}' in out
