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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        preview = self.text[:60] + ('…' if len(self.text) > 60 else '')
        return f"[{self.difficulty}] {preview}"


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
