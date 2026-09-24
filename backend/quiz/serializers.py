from rest_framework import serializers

from .models import Question, Choice


class DatabaseIDField(serializers.IntegerField):
    """Accept unambiguous JSON integers that fit a positive database bigint."""

    def __init__(self, **kwargs):
        super().__init__(min_value=1, max_value=2**63 - 1, **kwargs)

    def to_internal_value(self, data):
        if type(data) is not int:
            self.fail('invalid')
        return super().to_internal_value(data)


class ChoicePublicSerializer(serializers.ModelSerializer):
    """Choice as shown to the user BEFORE answering — no is_correct, no explanation leaked."""

    class Meta:
        model = Choice
        fields = ['id', 'text']


class QuestionSerializer(serializers.ModelSerializer):
    choices = ChoicePublicSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ['id', 'text', 'code_snippet', 'difficulty', 'module', 'choices']


class QuestionSearchSerializer(serializers.ModelSerializer):
    """Search preview without choices or answer-related fields."""

    class Meta:
        model = Question
        fields = ['id', 'text', 'code_snippet', 'difficulty', 'module']


class AnswerRequestSerializer(serializers.Serializer):
    choice_id = DatabaseIDField()


class AnswerItemSerializer(serializers.Serializer):
    question_id = DatabaseIDField()
    # null/omitted = the question was left unanswered (counts as wrong).
    choice_id = DatabaseIDField(required=False, allow_null=True, default=None)


class GradeRequestSerializer(serializers.Serializer):
    answers = AnswerItemSerializer(many=True, allow_empty=False, max_length=100)

    def validate_answers(self, answers):
        ids = [answer['question_id'] for answer in answers]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError('Each question may appear only once.')
        return answers
