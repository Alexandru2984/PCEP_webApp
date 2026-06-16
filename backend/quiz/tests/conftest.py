import pytest
from rest_framework.test import APIClient

from quiz.models import Choice, Question


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def make_question(db):
    """Factory: create a Question with four choices (exactly one correct)."""
    def _make(module=Question.MODULE_1, difficulty=Question.DIFFICULTY_EASY, correct_index=0):
        q = Question.objects.create(
            text='Sample question?',
            code_snippet='print(1)',
            module=module,
            difficulty=difficulty,
        )
        for i in range(4):
            Choice.objects.create(
                question=q,
                text=f'Choice {i}',
                is_correct=(i == correct_index),
                explanation=f'Explanation for choice {i}.',
            )
        return q
    return _make


@pytest.fixture
def question_bank(make_question):
    """Small mixed bank across modules and difficulties."""
    make_question(module=Question.MODULE_1, difficulty=Question.DIFFICULTY_EASY)
    make_question(module=Question.MODULE_1, difficulty=Question.DIFFICULTY_HARD)
    make_question(module=Question.MODULE_2, difficulty=Question.DIFFICULTY_MEDIUM)
    make_question(module=Question.MODULE_3, difficulty=Question.DIFFICULTY_HARD)
    make_question(module=Question.MODULE_4, difficulty=Question.DIFFICULTY_EASY)
