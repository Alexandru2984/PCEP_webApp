from django.contrib import admin
from .models import Question, Choice


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 4
    fields = ('text', 'is_correct', 'explanation')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'short_text', 'difficulty', 'updated_at')
    list_filter = ('difficulty',)
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

    @admin.display(description='Choice')
    def short_text(self, obj):
        return (obj.text[:80] + '…') if len(obj.text) > 80 else obj.text
