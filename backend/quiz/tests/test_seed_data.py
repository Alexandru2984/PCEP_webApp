from quiz.question_bank import (
    duplicate_questions,
    question_bank_summary,
    validation_errors,
)
from quiz.seed_data import ALL_QUESTIONS


VALID_MODULES = {'module1', 'module2', 'module3', 'module4'}
VALID_DIFFICULTIES = {'easy', 'medium', 'hard'}


def test_every_question_has_exactly_one_correct_choice():
    for q in ALL_QUESTIONS:
        n_correct = sum(1 for c in q['choices'] if c['is_correct'])
        assert n_correct == 1, f'Question {q["text"]!r} has {n_correct} correct choices'


def test_every_question_has_four_choices():
    for q in ALL_QUESTIONS:
        assert len(q['choices']) == 4, f'Question {q["text"]!r} has {len(q["choices"])} choices'


def test_every_choice_has_nonempty_explanation():
    for q in ALL_QUESTIONS:
        for c in q['choices']:
            assert c['explanation'].strip(), (
                f'Empty explanation under question {q["text"]!r}, choice {c["text"]!r}'
            )


def test_every_question_has_valid_module_and_difficulty():
    for q in ALL_QUESTIONS:
        assert q['module'] in VALID_MODULES
        assert q['difficulty'] in VALID_DIFFICULTIES


def test_bank_covers_all_four_modules():
    modules = {q['module'] for q in ALL_QUESTIONS}
    assert modules == VALID_MODULES


def test_question_bank_has_no_shape_errors():
    assert validation_errors() == []


def test_question_bank_summary_counts_every_question():
    summary = question_bank_summary()
    assert summary['total'] == len(ALL_QUESTIONS)
    assert sum(summary['by_module'].values()) == len(ALL_QUESTIONS)
    assert sum(summary['by_difficulty'].values()) == len(ALL_QUESTIONS)


def test_question_bank_has_no_duplicate_prompts():
    assert duplicate_questions() == []


def test_each_module_has_enough_hard_questions():
    summary = question_bank_summary()
    assert summary['warnings'] == []
