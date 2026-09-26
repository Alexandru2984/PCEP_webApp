"""Controlled PCEP-30-02 objective taxonomy for the question bank."""

from __future__ import annotations

import hashlib


OBJECTIVE_CHOICES = (
    ('1.1', '1.1 Fundamental terms and definitions'),
    ('1.2', '1.2 Python logic and structure'),
    ('1.3', '1.3 Literals, variables, and numeral systems'),
    ('1.4', '1.4 Operators and data types'),
    ('1.5', '1.5 Console input and output'),
    ('2.1', '2.1 Decisions and branching'),
    ('2.2', '2.2 Iteration and loop control'),
    ('3.1', '3.1 Lists'),
    ('3.2', '3.2 Tuples'),
    ('3.3', '3.3 Dictionaries'),
    ('3.4', '3.4 Strings'),
    ('4.1', '4.1 Functions and return values'),
    ('4.2', '4.2 Function arguments and scope'),
    ('4.3', '4.3 Built-in exception hierarchy'),
    ('4.4', '4.4 Exception handling'),
)

OBJECTIVE_LABELS = dict(OBJECTIVE_CHOICES)
OBJECTIVE_MODULE = {
    objective: f'module{objective[0]}' for objective in OBJECTIVE_LABELS
}
OBJECTIVES_BY_MODULE = {
    module: tuple(
        objective
        for objective in OBJECTIVE_LABELS
        if OBJECTIVE_MODULE[objective] == module
    )
    for module in ('module1', 'module2', 'module3', 'module4')
}


def _positions(*values):
    """Build a position set while keeping the curated table readable."""
    result = set()
    for value in values:
        if isinstance(value, range):
            result.update(value)
        else:
            result.add(value)
    return frozenset(result)


# Positions are one-based within each module. Every position is assigned exactly
# once. The module digest below prevents a reorder or content edit from silently
# attaching an old objective to a different question.
CURATED_POSITIONS = {
    'module1': {
        '1.1': _positions(74, 75),
        '1.2': _positions(76, 77),
        '1.3': _positions(10, 13, range(19, 23), 25, 26, 31, 33, 39, 44, 51, 64, 65),
        '1.4': _positions(
            range(1, 7), 9, 12, range(14, 18), 23, 24, 28, 30,
            34, 35, range(37, 39), range(40, 44), range(45, 51),
            range(52, 56), range(57, 64), range(66, 74),
        ),
        '1.5': _positions(7, 8, 11, 18, 27, 29, 32, 36, 56),
    },
    'module2': {
        '2.1': _positions(
            range(1, 6), 15, 18, 19, 23, 24, 25, 28, 29, 32, 34,
            39, 42, 48, 49, 50, 57, 59, 62, 66, 67, 69, 71, 73,
        ),
        '2.2': _positions(
            range(6, 15), 16, 17, range(20, 23), 26, 27, 30, 31, 33,
            range(35, 39), 40, 41, range(43, 48), range(51, 57),
            58, 60, 61, range(63, 66), 68, 70, 72,
        ),
    },
    'module3': {
        '3.1': _positions(
            range(1, 14), range(24, 28), 35, 40, 42, 45, 46, 47, 49, 51, 54, 55,
            59, 63, 64, 65, 66, 70, 71, 72, 74, 76, 79, 82, 83,
        ),
        '3.2': _positions(14, 15, 16, 38, 58, 67, 81, 84),
        '3.3': _positions(
            17, 18, 19, 28, 29, 34, 37, 39, 44, 48, 56, 57, 62,
            68, 69, 77,
        ),
        '3.4': _positions(
            range(20, 24), range(30, 34), 36, 41, 43, 50, 52, 53,
            60, 61, 73, 75, 78, 80, 85,
        ),
    },
    'module4': {
        '4.1': _positions(
            1, 6, 7, 8, 18, 24, 29, 32, 33, 41, 42, 49, 53,
            56, 59, 60, 63, 65, 69,
        ),
        '4.2': _positions(
            range(2, 6), 9, 10, 16, 17, 19, 22, 26, 27, 28,
            range(34, 36), range(37, 41), 43, 44, 48, range(50, 53),
            57, 58, 61, 62, 66, 68, 70,
        ),
        '4.3': _positions(13, 14, 15, 25, 36, 47, 64),
        '4.4': _positions(11, 12, 20, 21, 23, 30, 31, 45, 46, 54, 55, 67),
    },
}

# Filled from the reviewed source bank. See ``module_signature`` and the tests;
# changing question content requires an explicit taxonomy review.
CURATED_MODULE_SIGNATURES = {
    'module1': '5403fa0735e92558617d0af0379d046f6f612f64816f9753412fcd77542293d6',
    'module2': '02757b38fed57d6ef9af4547b75cd5afeb4d44a8eae65365666f8f12105629b1',
    'module3': '20650437f03178805fd5b1c91c4839904f7853194bded285be783577acb7df06',
    'module4': 'a3d3b8764dba02f496bc9dd00e6574cdb9f42156bb40e803b1d516e2a00f5967',
}


def module_signature(questions):
    digest = hashlib.sha256()
    for question in questions:
        digest.update(question.get('text', '').encode('utf-8'))
        digest.update(b'\0')
        digest.update(question.get('code_snippet', '').encode('utf-8'))
        digest.update(b'\0')
    return digest.hexdigest()


def apply_objectives(module, questions):
    """Return seed rows with their reviewed primary syllabus objective."""
    assignments = CURATED_POSITIONS[module]
    by_position = {}
    for objective, positions in assignments.items():
        if OBJECTIVE_MODULE.get(objective) != module:
            raise RuntimeError(f'{objective} does not belong to {module}')
        for position in positions:
            if position in by_position:
                raise RuntimeError(f'{module} question #{position} has two objectives')
            by_position[position] = objective

    expected = set(range(1, len(questions) + 1))
    assigned = set(by_position)
    if assigned != expected:
        missing = sorted(expected - assigned)
        extra = sorted(assigned - expected)
        raise RuntimeError(
            f'{module} objective map does not match the bank; '
            f'missing={missing}, extra={extra}'
        )

    expected_signature = CURATED_MODULE_SIGNATURES[module]
    actual_signature = module_signature(questions)
    if expected_signature and actual_signature != expected_signature:
        raise RuntimeError(
            f'{module} content changed; review objective assignments and update its digest'
        )

    return [
        {**question, 'module': module, 'objective': by_position[position]}
        for position, question in enumerate(questions, start=1)
    ]
