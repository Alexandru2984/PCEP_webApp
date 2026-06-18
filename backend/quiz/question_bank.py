from collections import Counter

from .seed_data import ALL_QUESTIONS


VALID_MODULES = ('module1', 'module2', 'module3', 'module4')
VALID_DIFFICULTIES = ('easy', 'medium', 'hard')
MIN_HARD_PER_MODULE = 8


def question_key(question):
    return (
        question.get('text', '').strip().casefold(),
        question.get('code_snippet', '').strip().casefold(),
    )


def duplicate_questions(questions=ALL_QUESTIONS):
    counts = Counter(question_key(q) for q in questions)
    duplicates = []
    for index, question in enumerate(questions, start=1):
        key = question_key(question)
        if counts[key] > 1:
            duplicates.append((index, question))
    return duplicates


def validation_errors(questions=ALL_QUESTIONS):
    errors = []
    valid_modules = set(VALID_MODULES)
    valid_difficulties = set(VALID_DIFFICULTIES)

    for index, question in enumerate(questions, start=1):
        label = f'question #{index}: {question.get("text", "")!r}'
        choices = question.get('choices', [])
        correct_count = sum(1 for c in choices if c.get('is_correct'))

        if question.get('module') not in valid_modules:
            errors.append(f'{label} has invalid module {question.get("module")!r}')
        if question.get('difficulty') not in valid_difficulties:
            errors.append(
                f'{label} has invalid difficulty {question.get("difficulty")!r}'
            )
        if len(choices) != 4:
            errors.append(f'{label} has {len(choices)} choices, expected 4')
        if correct_count != 1:
            errors.append(f'{label} has {correct_count} correct choices, expected 1')
        for choice_index, choice in enumerate(choices, start=1):
            if not choice.get('explanation', '').strip():
                errors.append(f'{label} choice #{choice_index} has empty explanation')

    return errors


def coverage_warnings(questions=ALL_QUESTIONS):
    summary = question_bank_summary(questions, include_warnings=False)
    warnings = []
    for module in VALID_MODULES:
        hard_count = summary['matrix'][module]['hard']
        if hard_count < MIN_HARD_PER_MODULE:
            warnings.append(
                f'{module} has {hard_count} hard questions, '
                f'expected at least {MIN_HARD_PER_MODULE}'
            )
    return warnings


def question_bank_summary(questions=ALL_QUESTIONS, include_warnings=True):
    by_module = Counter(q.get('module') for q in questions)
    by_difficulty = Counter(q.get('difficulty') for q in questions)
    matrix = {
        module: {
            difficulty: sum(
                1
                for q in questions
                if q.get('module') == module and q.get('difficulty') == difficulty
            )
            for difficulty in VALID_DIFFICULTIES
        }
        for module in VALID_MODULES
    }
    summary = {
        'total': len(questions),
        'by_module': by_module,
        'by_difficulty': by_difficulty,
        'matrix': matrix,
        'duplicates': duplicate_questions(questions),
        'errors': validation_errors(questions),
    }
    if include_warnings:
        summary['warnings'] = coverage_warnings(questions)
    return summary
