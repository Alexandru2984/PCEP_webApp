from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from .models import Question, Choice


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


class ChoiceInline(admin.TabularInline):
    model = Choice
    formset = ChoiceFormSet
    extra = 4
    fields = ('text', 'is_correct', 'explanation')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'short_text', 'module', 'difficulty', 'updated_at')
    list_filter = ('module', 'difficulty')
    search_fields = ('text', 'code_snippet')
    inlines = [ChoiceInline]

    @admin.display(description='Question')
    def short_text(self, obj):
        return (obj.text[:80] + '…') if len(obj.text) > 80 else obj.text


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
