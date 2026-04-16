from rest_framework import serializers

from .models import Question, Choice


class ChoicePublicSerializer(serializers.ModelSerializer):
    """Choice as shown to the user BEFORE answering — no is_correct, no explanation leaked."""

    class Meta:
        model = Choice
        fields = ['id', 'text']


class QuestionSerializer(serializers.ModelSerializer):
    choices = ChoicePublicSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ['id', 'text', 'code_snippet', 'difficulty', 'choices']


class AnswerRequestSerializer(serializers.Serializer):
    choice_id = serializers.IntegerField()
