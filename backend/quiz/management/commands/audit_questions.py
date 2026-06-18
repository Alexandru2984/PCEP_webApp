from django.core.management.base import BaseCommand, CommandError

from quiz.question_bank import (
    VALID_DIFFICULTIES,
    VALID_MODULES,
    question_bank_summary,
)


class Command(BaseCommand):
    help = 'Audit the seeded PCEP question bank for coverage and data integrity.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fail-on-warnings',
            action='store_true',
            help='Exit non-zero when duplicates are found.',
        )

    def handle(self, *args, **options):
        summary = question_bank_summary()

        self.stdout.write(f'Total questions: {summary["total"]}')
        self.stdout.write('\nBy module:')
        for module in VALID_MODULES:
            self.stdout.write(f'  {module}: {summary["by_module"].get(module, 0)}')

        self.stdout.write('\nBy difficulty:')
        for difficulty in VALID_DIFFICULTIES:
            self.stdout.write(
                f'  {difficulty}: {summary["by_difficulty"].get(difficulty, 0)}'
            )

        self.stdout.write('\nModule/difficulty matrix:')
        for module in VALID_MODULES:
            row = summary['matrix'][module]
            self.stdout.write(
                f'  {module}: '
                + ', '.join(f'{d}={row[d]}' for d in VALID_DIFFICULTIES)
            )

        if summary['errors']:
            self.stdout.write(self.style.ERROR('\nData errors:'))
            for error in summary['errors']:
                self.stdout.write(f'  - {error}')
            raise CommandError('Question bank has data errors.')

        if summary['duplicates']:
            self.stdout.write(self.style.WARNING('\nDuplicate question prompts:'))
            for index, question in summary['duplicates']:
                self.stdout.write(
                    f'  - #{index} [{question["module"]}/{question["difficulty"]}] '
                    f'{question["text"]} | {question.get("code_snippet", "")!r}'
                )
            if options['fail_on_warnings']:
                raise CommandError('Question bank has duplicate prompts.')

        self.stdout.write(self.style.SUCCESS('\nQuestion bank audit complete.'))
