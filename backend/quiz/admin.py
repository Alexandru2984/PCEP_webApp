from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from .models import Question, Choice
from .question_bank import question_key, syllabus_warnings, validation_errors


class ChoiceFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        choices = [f.cleaned_data for f in self.forms
                   if f.cleaned_data and not f.cleaned_data.get('DELETE')]
        if len(choices) != 4:
            raise ValidationError('A question must have exactly four choices.')
        if sum(c.get('is_correct', False) for c in choices) != 1:
            raise ValidationError('Select exactly one correct choice.')
        texts = [c.get('text', '').strip() for c in choices]
        if any(not t for t in texts) or len(set(texts)) != len(texts):
            raise ValidationError('Choice text must be non-empty and unique.')
        if any(not c.get('explanation', '').strip() for c in choices):
            raise ValidationError('Explain every choice before saving the question.')

        candidate = {
            'text': self.instance.text,
            'code_snippet': self.instance.code_snippet,
            'module': self.instance.module,
            'objective': self.instance.objective,
            'difficulty': self.instance.difficulty,
            'choices': [
                {
                    'text': choice['text'],
                    'is_correct': choice.get('is_correct', False),
                    'explanation': choice['explanation'],
                }
                for choice in choices
            ],
        }
        def admin_label(_question, _index):
            return 'This question'

        quality_errors = validation_errors([candidate], labeler=admin_label)
        scope_warnings = syllabus_warnings([candidate], labeler=admin_label)
        if quality_errors or scope_warnings:
            raise ValidationError(quality_errors + scope_warnings)

        candidate_key = question_key(candidate)
        duplicate_ids = [
            row['id']
            for row in Question.objects.exclude(pk=self.instance.pk).values(
                'id', 'text', 'code_snippet'
            )
            if question_key(row) == candidate_key
        ]
        if duplicate_ids:
            ids = ', '.join(str(question_id) for question_id in duplicate_ids[:5])
            raise ValidationError(
                f'This prompt and code duplicate existing question ID {ids}.'
            )


class ChoiceInline(admin.TabularInline):
    model = Choice
    formset = ChoiceFormSet
    extra = 4
    fields = ('text', 'is_correct', 'explanation')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'short_text',
        'correct_answer',
        'module',
        'objective',
        'difficulty',
        'updated_at',
    )
    list_filter = ('module', 'objective', 'difficulty')
    search_fields = ('text', 'code_snippet')
    inlines = [ChoiceInline]

    @admin.display(description='Question')
    def short_text(self, obj):
        return (obj.text[:80] + '…') if len(obj.text) > 80 else obj.text

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('choices')

    @admin.display(description='Correct answer')
    def correct_answer(self, obj):
        correct = [choice for choice in obj.choices.all() if choice.is_correct]
        if len(correct) != 1:
            return f'⚠ {len(correct)} correct choices'
        text = correct[0].text
        return (text[:60] + '…') if len(text) > 60 else text


@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'question', 'short_text', 'is_correct')
    list_filter = ('is_correct',)
    search_fields = ('text', 'explanation')
    list_select_related = ('question',)
    readonly_fields = ('question', 'text', 'is_correct', 'explanation')

    # Editing options in isolation bypasses question-level answer validation.
    # Keep this list available for inspection; edit through the question inline.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Choice')
    def short_text(self, obj):
        return (obj.text[:80] + '…') if len(obj.text) > 80 else obj.text
