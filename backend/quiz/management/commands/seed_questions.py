"""
Seed the database with PCEP quiz questions.

Usage (inside the backend container):
    python manage.py seed_questions           # add questions (duplicates if run twice)
    python manage.py seed_questions --reset   # wipe all questions then seed
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from quiz.models import Choice, Question
from quiz.seed_data import ALL_QUESTIONS


class Command(BaseCommand):
    help = 'Seed the database with PCEP quiz questions covering the full PCEP-30-02 syllabus.'

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
        for q in ALL_QUESTIONS:
            question = Question.objects.create(
                text=q['text'],
                code_snippet=q.get('code_snippet', ''),
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
