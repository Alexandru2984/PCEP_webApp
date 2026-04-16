"""
Seed the database with demo PCEP questions.

Usage (inside the backend container):
    python manage.py seed_questions           # add demo questions
    python manage.py seed_questions --reset   # wipe + reseed
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from quiz.models import Question, Choice


QUESTIONS = [
    # Q1 — scopes (LEGB rule)
    {
        'text': 'What is printed by the following code?',
        'code_snippet': (
            'x = 10\n'
            'def f():\n'
            '    x = 20\n'
            '    print(x)\n'
            'f()\n'
            'print(x)'
        ),
        'difficulty': 'easy',
        'choices': [
            {
                'text': '10, then 20',
                'is_correct': False,
                'explanation': (
                    'Wrong order. Inside f() the assignment creates a LOCAL variable x bound to 20, '
                    'so f() prints 20 first. The global x is still 10 and is printed second.'
                ),
            },
            {
                'text': '20, then 10',
                'is_correct': True,
                'explanation': (
                    'Correct. Python uses the LEGB scope rule: inside f() the assignment x = 20 '
                    'creates a NEW local binding that shadows the global. The global x remains 10.'
                ),
            },
            {
                'text': '20, then 20',
                'is_correct': False,
                'explanation': (
                    "Wrong. f() did not modify the global x because it did not use the `global` "
                    'keyword. The assignment x = 20 created a local name, visible only inside f().'
                ),
            },
            {
                'text': '10, then 10',
                'is_correct': False,
                'explanation': (
                    'Wrong. Inside f() the local assignment takes effect, so print(x) there outputs 20, not 10.'
                ),
            },
        ],
    },
    # Q2 — mutability / aliasing
    {
        'text': 'What is the value of `a` after running this code?',
        'code_snippet': (
            'a = [1, 2, 3]\n'
            'b = a\n'
            'b.append(4)\n'
            'print(a)'
        ),
        'difficulty': 'medium',
        'choices': [
            {
                'text': '[1, 2, 3]',
                'is_correct': False,
                'explanation': (
                    'Wrong. `b = a` does NOT copy the list — it binds the name b to the same list '
                    'object that a references. Mutating via b is visible through a.'
                ),
            },
            {
                'text': '[1, 2, 3, 4]',
                'is_correct': True,
                'explanation': (
                    'Correct. Lists are mutable and `b = a` creates an alias, not a copy. '
                    'append() mutates the single underlying list, so printing a shows the appended 4.'
                ),
            },
            {
                'text': '[4, 1, 2, 3]',
                'is_correct': False,
                'explanation': (
                    'Wrong. list.append() adds to the END of the list. For an insertion at the front '
                    'you would use a.insert(0, 4).'
                ),
            },
            {
                'text': 'TypeError',
                'is_correct': False,
                'explanation': (
                    'Wrong. Every operation here is valid — no exception is raised. append() is a '
                    'standard list method and aliasing a list is legal in Python.'
                ),
            },
        ],
    },
    # Q3 — loops / range
    {
        'text': 'How many times does the loop body execute? (i.e. final value of `total`)',
        'code_snippet': (
            'total = 0\n'
            'for i in range(2, 10, 3):\n'
            '    total += 1\n'
            'print(total)'
        ),
        'difficulty': 'easy',
        'choices': [
            {
                'text': '2',
                'is_correct': False,
                'explanation': (
                    'Wrong. range(2, 10, 3) yields 2, 5, 8 — three values — so the loop runs 3 times, not 2.'
                ),
            },
            {
                'text': '3',
                'is_correct': True,
                'explanation': (
                    'Correct. range(start, stop, step) yields start, start+step, start+2*step, ... '
                    'while the value is strictly less than stop. range(2, 10, 3) → 2, 5, 8. '
                    'The next would be 11, which is NOT < 10, so iteration stops.'
                ),
            },
            {
                'text': '4',
                'is_correct': False,
                'explanation': (
                    'Wrong. `stop` in range() is EXCLUSIVE — 10 is never reached, and 11 is past it. '
                    'Values yielded are 2, 5, 8 only.'
                ),
            },
            {
                'text': '8',
                'is_correct': False,
                'explanation': (
                    'Wrong. 8 is the LAST value yielded by range(2, 10, 3), not the count. '
                    'The count is 3.'
                ),
            },
        ],
    },
]


class Command(BaseCommand):
    help = 'Seed the database with demo PCEP quiz questions.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete all existing questions (and their choices, via cascade) before seeding.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options['reset']:
            count = Question.objects.count()
            Question.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'Deleted {count} existing question(s).'))

        created = 0
        for q in QUESTIONS:
            question = Question.objects.create(
                text=q['text'],
                code_snippet=q['code_snippet'],
                difficulty=q['difficulty'],
            )
            for c in q['choices']:
                Choice.objects.create(
                    question=question,
                    text=c['text'],
                    is_correct=c['is_correct'],
                    explanation=c['explanation'],
                )
            created += 1

        self.stdout.write(self.style.SUCCESS(f'Seeded {created} question(s) successfully.'))
