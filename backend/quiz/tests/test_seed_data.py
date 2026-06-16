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
