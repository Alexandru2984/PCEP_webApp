from django.db import models


class Question(models.Model):
    DIFFICULTY_EASY = 'easy'
    DIFFICULTY_MEDIUM = 'medium'
    DIFFICULTY_HARD = 'hard'
    DIFFICULTY_CHOICES = [
        (DIFFICULTY_EASY, 'Easy'),
        (DIFFICULTY_MEDIUM, 'Medium'),
        (DIFFICULTY_HARD, 'Hard'),
    ]

    MODULE_1 = 'module1'
    MODULE_2 = 'module2'
    MODULE_3 = 'module3'
    MODULE_4 = 'module4'
    MODULE_CHOICES = [
        (MODULE_1, 'Module 1 — Fundamentals'),
        (MODULE_2, 'Module 2 — Control Flow'),
        (MODULE_3, 'Module 3 — Data Collections'),
        (MODULE_4, 'Module 4 — Functions & Exceptions'),
    ]

    text = models.TextField(help_text="Main question text shown to the user.")
    code_snippet = models.TextField(
        blank=True,
        default='',
        help_text="Optional Python code snippet displayed alongside the question.",
    )
    difficulty = models.CharField(
        max_length=16,
        choices=DIFFICULTY_CHOICES,
        default=DIFFICULTY_MEDIUM,
    )
    module = models.CharField(
        max_length=16,
        choices=MODULE_CHOICES,
        default=MODULE_1,
        db_index=True,
        help_text="PCEP-30-02 syllabus module this question belongs to.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        preview = self.text[:60] + ('…' if len(self.text) > 60 else '')
        return f"[{self.module}/{self.difficulty}] {preview}"


class Choice(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='choices',
    )
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    explanation = models.TextField(
        blank=True,
        default='',
        help_text=(
            "Shown after the user picks this option. For wrong choices, "
            "explain WHY this option is wrong. For the correct choice, "
            "explain the underlying Python concept."
        ),
    )

    class Meta:
        ordering = ['id']

    def __str__(self):
        mark = '✓' if self.is_correct else '✗'
        preview = self.text[:60] + ('…' if len(self.text) > 60 else '')
        return f"{mark} {preview}"
