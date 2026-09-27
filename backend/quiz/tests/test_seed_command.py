from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

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


def test_seed_questions_update_refreshes_choices_without_changing_ids():
    run_seed()
    question = Question.objects.first()
    choice_ids = list(question.choices.order_by('id').values_list('id', flat=True))
    changed_choice = question.choices.order_by('id').first()
    changed_choice.text = 'A temporary operator edit'
    changed_choice.explanation = 'Temporary explanation'
    changed_choice.save(update_fields=['text', 'explanation'])
    expected_difficulty = ALL_QUESTIONS[0]['difficulty']
    question.difficulty = (
        Question.DIFFICULTY_HARD
        if expected_difficulty != Question.DIFFICULTY_HARD
        else Question.DIFFICULTY_EASY
    )
    expected_objective = ALL_QUESTIONS[0]['objective']
    question.objective = '1.1' if expected_objective != '1.1' else '1.2'
    question.save(update_fields=['difficulty', 'objective'])

    out = run_seed('--update')

    question.refresh_from_db()
    assert question.choices.count() == 4
    assert list(question.choices.order_by('id').values_list('id', flat=True)) == choice_ids
    assert list(
        question.choices.order_by('id').values('text', 'is_correct', 'explanation')
    ) == ALL_QUESTIONS[0]['choices']
    assert question.difficulty == expected_difficulty
    assert question.objective == expected_objective
    assert f'updated={len(ALL_QUESTIONS)}' in out


def test_seed_questions_update_refuses_structural_choice_changes_atomically():
    run_seed()
    first = Question.objects.order_by('id').first()
    original_difficulty = first.difficulty
    changed_difficulty = (
        Question.DIFFICULTY_HARD
        if original_difficulty != Question.DIFFICULTY_HARD
        else Question.DIFFICULTY_EASY
    )
    first.difficulty = changed_difficulty
    first.save(update_fields=['difficulty'])
    malformed = Question.objects.order_by('id')[1]
    malformed.choices.order_by('id').first().delete()

    with pytest.raises(CommandError, match='reviewed data migration'):
        run_seed('--update')

    first.refresh_from_db()
    malformed.refresh_from_db()
    assert first.difficulty == changed_difficulty
    assert malformed.choices.count() == 3


def test_seed_questions_dry_run_does_not_write():
    out = run_seed('--dry-run')

    assert Question.objects.count() == 0
    assert 'Dry run' in out
    assert f'Would create {len(ALL_QUESTIONS)}' in out
