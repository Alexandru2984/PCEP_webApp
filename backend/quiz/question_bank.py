import ast
import re
from collections import Counter
from difflib import SequenceMatcher

from .seed_data import ALL_QUESTIONS
from .syllabus import OBJECTIVE_LABELS, OBJECTIVE_MODULE


VALID_MODULES = ('module1', 'module2', 'module3', 'module4')
VALID_DIFFICULTIES = ('easy', 'medium', 'hard')
VALID_OBJECTIVES = tuple(OBJECTIVE_LABELS)
MIN_HARD_PER_MODULE = 8
NEAR_DUPLICATE_THRESHOLD = 0.96

# These pairs intentionally share a setup so learners can contrast one changed
# rule: alias versus slice copy, negative index versus slice step, and skipping
# one value versus all even values. Exact prompt/code keys make any future edit
# fall back into the review queue.
REVIEWED_DISTINCT_PAIRS = frozenset(
    {
        frozenset(
            {
                (
                    'What is the output?',
                    'a = [1, 2, 3]\nb = a\nb.append(4)\nprint(len(a))',
                ),
                (
                    'What is the output?',
                    'a = [1, 2, 3]\nb = a[:]\nb.append(4)\nprint(len(a))',
                ),
            }
        ),
        frozenset(
            {
                (
                    'What does this print?',
                    'lst = [10, 20, 30, 40, 50]\nprint(lst[-2])',
                ),
                (
                    'What does this print?',
                    'lst = [10, 20, 30, 40, 50]\nprint(lst[::2])',
                ),
            }
        ),
        frozenset(
            {
                (
                    'What does this print?',
                    "for i in range(5):\n    if i == 2:\n        continue\n    print(i, end=' ')",
                ),
                (
                    'What does this print?',
                    "for i in range(5):\n    if i % 2 == 0:\n        continue\n    print(i, end=' ')",
                ),
            }
        ),
    }
)


def question_key(question):
    text = ' '.join(question.get('text', '').casefold().split())
    snippet = question.get('code_snippet', '').strip()
    if snippet:
        try:
            # Ignore quote style and harmless formatting when the snippet is valid
            # Python. Invalid snippets are sometimes intentional teaching examples,
            # so they fall back to normalized source instead of becoming audit errors.
            snippet = ast.dump(ast.parse(snippet), include_attributes=False)
        except (SyntaxError, ValueError):
            snippet = ' '.join(snippet.split())
    return (
        text,
        snippet,
    )


def duplicate_questions(questions=ALL_QUESTIONS):
    counts = Counter(question_key(q) for q in questions)
    duplicates = []
    for index, question in enumerate(questions, start=1):
        key = question_key(question)
        if counts[key] > 1:
            duplicates.append((index, question))
    return duplicates


def similar_questions(questions=ALL_QUESTIONS, threshold=NEAR_DUPLICATE_THRESHOLD):
    """Return high-similarity candidates for human review, excluding exact matches."""
    prepared = [
        (
            index,
            question,
            question_key(question),
            '\n'.join(
                (
                    ' '.join(question.get('text', '').casefold().split()),
                    ' '.join(question.get('code_snippet', '').split()),
                )
            ),
        )
        for index, question in enumerate(questions, start=1)
    ]
    candidates = []
    for position, first in enumerate(prepared):
        for second in prepared[position + 1:]:
            if first[1].get('module') != second[1].get('module'):
                continue
            if first[2] == second[2]:
                continue
            review_pair = frozenset(
                {
                    (
                        first[1].get('text', '').strip(),
                        first[1].get('code_snippet', '').strip(),
                    ),
                    (
                        second[1].get('text', '').strip(),
                        second[1].get('code_snippet', '').strip(),
                    ),
                }
            )
            if review_pair in REVIEWED_DISTINCT_PAIRS:
                continue
            similarity = SequenceMatcher(
                None, first[3], second[3], autojunk=False
            ).ratio()
            if similarity >= threshold:
                candidates.append(
                    (first[0], second[0], similarity, first[1], second[1])
                )
    return sorted(candidates, key=lambda item: (-item[2], item[0], item[1]))


def validation_errors(questions=ALL_QUESTIONS):
    errors = []
    valid_modules = set(VALID_MODULES)
    valid_difficulties = set(VALID_DIFFICULTIES)

    for index, question in enumerate(questions, start=1):
        label = f'question #{index}: {question.get("text", "")!r}'
        if 'id' in question:
            label = f'database question id={question["id"]}: {question.get("text", "")!r}'
        choices = question.get('choices', [])
        correct_count = sum(1 for c in choices if c.get('is_correct'))

        if not question.get('text', '').strip():
            errors.append(f'{label} has empty question text')
        if question.get('module') not in valid_modules:
            errors.append(f'{label} has invalid module {question.get("module")!r}')
        if question.get('difficulty') not in valid_difficulties:
            errors.append(
                f'{label} has invalid difficulty {question.get("difficulty")!r}'
            )
        objective = question.get('objective')
        if objective not in OBJECTIVE_LABELS:
            errors.append(f'{label} has invalid objective {objective!r}')
        elif OBJECTIVE_MODULE[objective] != question.get('module'):
            errors.append(
                f'{label} objective {objective!r} does not belong to '
                f'{question.get("module")!r}'
            )
        if len(choices) != 4:
            errors.append(f'{label} has {len(choices)} choices, expected 4')
        if correct_count != 1:
            errors.append(f'{label} has {correct_count} correct choices, expected 1')
        texts = [c.get('text', '').strip() for c in choices]
        if len(texts) != len(set(texts)):
            errors.append(f'{label} has duplicate option text')
        for choice_index, choice in enumerate(choices, start=1):
            if not choice.get('text', '').strip():
                errors.append(f'{label} choice #{choice_index} has empty text')
            if len(choice.get('text', '')) > 500:
                errors.append(f'{label} choice #{choice_index} exceeds 500 characters')
            if type(choice.get('is_correct')) is not bool:
                errors.append(f'{label} choice #{choice_index} has a non-boolean answer flag')
            if not choice.get('explanation', '').strip():
                errors.append(f'{label} choice #{choice_index} has empty explanation')

    return errors


def syllabus_warnings(questions=ALL_QUESTIONS):
    warnings = []
    for index, question in enumerate(questions, start=1):
        snippet = question.get('code_snippet', '').strip()
        label = f'question #{index}'
        if 'id' in question:
            label = f'database question id={question["id"]}'

        nodes = ()
        if snippet:
            try:
                nodes = tuple(ast.walk(ast.parse(snippet)))
            except (SyntaxError, ValueError):
                # Some questions intentionally demonstrate invalid syntax. Their
                # explanatory text still participates in the scope audit.
                pass

        checks = (
            (
                any(
                    isinstance(node, (ast.Set, ast.SetComp))
                    or (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == 'set'
                    )
                    for node in nodes
                ),
                'uses sets, which are outside the PCEP-30-02 data-collection objectives',
            ),
            (
                any(isinstance(node, ast.Lambda) for node in nodes),
                'uses lambda expressions, which are outside the PCEP-30-02 function objectives',
            ),
            (
                any(isinstance(node, ast.Nonlocal) for node in nodes),
                'uses `nonlocal`, while PCEP-30-02 scope coverage stops at `global`',
            ),
            (
                any(isinstance(node, ast.Assert) for node in nodes),
                'uses `assert`/`AssertionError`, which are outside the PCEP-30-02 exception objectives',
            ),
            (
                any(
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, complex)
                    for node in nodes
                ),
                'uses complex literals, while PCEP-30-02 numeric literals cover integers and floats',
            ),
            (
                any(isinstance(node, ast.DictComp) for node in nodes),
                'uses dictionary comprehensions, while PCEP-30-02 names only list comprehensions',
            ),
            (
                any(isinstance(node, ast.Starred) for node in nodes),
                'uses starred unpacking, which is outside the PCEP-30-02 collection objectives',
            ),
            (
                any(isinstance(node, ast.JoinedStr) for node in nodes),
                'uses f-strings, which are outside the PCEP-30-02 string objectives',
            ),
            (
                any(
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == 'enumerate'
                    for node in nodes
                ),
                'uses `enumerate()`, which is outside the PCEP-30-02 collection objectives',
            ),
            (
                any(
                    isinstance(node, ast.Attribute)
                    and node.attr == '__name__'
                    for node in nodes
                ),
                'uses `__name__` introspection, which is outside the PCEP-30-02 objectives',
            ),
        )
        warnings.extend(f'{label} {message}' for matched, message in checks if matched)

        explanatory_text = ' '.join(
            [question.get('text', '')]
            + [
                f'{choice.get("text", "")} {choice.get("explanation", "")}'
                for choice in question.get('choices', [])
            ]
        )
        reference_checks = (
            (r'\blambda\b', 'lambda expressions'),
            (r'\bnonlocal\b', '`nonlocal`'),
            (r'\b(?:assert|assertionerror)\b', '`assert`/`AssertionError`'),
            (r'\bcomplex\b', 'complex numbers'),
            (r'\bdict(?:ionary)? comprehensions?\b', 'dictionary comprehensions'),
            (r'\bstarred unpacking\b', 'starred unpacking'),
            (r'\bf-strings?\b', 'f-strings'),
            (r'\benumerate\s*\(', '`enumerate()`'),
            (r'__name__', '`__name__` introspection'),
        )
        warnings.extend(
            f'{label} references {description}, which is outside the reviewed '
            'PCEP-30-02 scope'
            for pattern, description in reference_checks
            if re.search(pattern, explanatory_text, flags=re.IGNORECASE)
        )
    return warnings


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
    for objective in VALID_OBJECTIVES:
        if summary['by_objective'].get(objective, 0) == 0:
            warnings.append(f'{objective} has no questions')
    return warnings + syllabus_warnings(questions)


def question_bank_summary(questions=ALL_QUESTIONS, include_warnings=True):
    by_module = Counter(q.get('module') for q in questions)
    by_difficulty = Counter(q.get('difficulty') for q in questions)
    by_objective = Counter(q.get('objective') for q in questions)
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
        'by_objective': by_objective,
        'matrix': matrix,
        'duplicates': duplicate_questions(questions),
        'errors': validation_errors(questions),
    }
    if include_warnings:
        summary['warnings'] = coverage_warnings(questions)
    return summary


def database_questions():
    """Private audit representation; never use this for a public response."""
    from .models import Question
    return [
        {
            'id': q.id, 'text': q.text, 'code_snippet': q.code_snippet,
            'module': q.module, 'difficulty': q.difficulty,
            'objective': q.objective,
            'choices': [
                {'text': c.text, 'is_correct': c.is_correct, 'explanation': c.explanation}
                for c in q.choices.all()
            ],
        }
        for q in Question.objects.prefetch_related('choices').iterator(chunk_size=200)
    ]
