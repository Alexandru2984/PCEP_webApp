"""
Seed the database with PCEP quiz questions.

Usage (inside the backend container):
    python manage.py seed_questions           # add missing questions, skip existing
    python manage.py seed_questions --update  # update existing questions and choices
    python manage.py seed_questions --reset   # wipe all questions then seed
    python manage.py seed_questions --dry-run # report planned changes only
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
        parser.add_argument(
            '--update',
            action='store_true',
            help='Update matching existing questions and recreate their choices.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would change without writing to the database.',
        )

    def handle(self, *args, **options):
        reset = options['reset']
        update = options['update']
        dry_run = options['dry_run']

        if dry_run:
            self._report_plan(reset=reset, update=update)
            return

        with transaction.atomic():
            deleted = 0
            if reset:
                deleted = Question.objects.count()
                Question.objects.all().delete()

            created, updated, skipped = self._seed(update=update)

        if reset:
            self.stdout.write(
                self.style.WARNING(f'Deleted {deleted} existing question(s).')
            )
        self.stdout.write(
            self.style.SUCCESS(
                f'Seed complete: created={created}, updated={updated}, skipped={skipped}.'
            )
        )

    def _report_plan(self, *, reset, update):
        existing_keys = set(
            Question.objects.values_list('module', 'text', 'code_snippet')
        )
        seed_keys = {
            (q.get('module', Question.MODULE_1), q['text'], q.get('code_snippet', ''))
            for q in ALL_QUESTIONS
        }
        existing_matches = len(existing_keys & seed_keys)
        missing = len(seed_keys - existing_keys)

        self.stdout.write('Dry run: no database writes will be made.')
        if reset:
            self.stdout.write(f'Would delete {Question.objects.count()} question(s).')
            self.stdout.write(f'Would create {len(ALL_QUESTIONS)} question(s).')
            return

        self.stdout.write(f'Would create {missing} missing question(s).')
        if update:
            self.stdout.write(f'Would update {existing_matches} existing question(s).')
        else:
            self.stdout.write(f'Would skip {existing_matches} existing question(s).')

    def _seed(self, *, update):
        created = 0
        updated = 0
        skipped = 0

        for q in ALL_QUESTIONS:
            module = q.get('module', Question.MODULE_1)
            code_snippet = q.get('code_snippet', '')
            question = Question.objects.filter(
                module=module,
                text=q['text'],
                code_snippet=code_snippet,
            ).first()

            if question is None:
                question = Question.objects.create(
                    text=q['text'],
                    code_snippet=code_snippet,
                    difficulty=q['difficulty'],
                    module=module,
                )
                self._replace_choices(question, q['choices'])
                created += 1
                continue

            if not update:
                skipped += 1
                continue

            question.difficulty = q['difficulty']
            question.save(update_fields=['difficulty', 'updated_at'])
            self._replace_choices(question, q['choices'])
            updated += 1

        return created, updated, skipped

    def _replace_choices(self, question, choices):
        question.choices.all().delete()
        Choice.objects.bulk_create(
            [
                Choice(
                    question=question,
                    text=c['text'],
                    is_correct=c['is_correct'],
                    explanation=c['explanation'],
                )
                for c in choices
            ]
        )
