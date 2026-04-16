from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response

from .models import Choice, Question
from .serializers import AnswerRequestSerializer, QuestionSerializer


@api_view(['GET'])
def quiz_set(request):
    """Return a randomized set of questions for a quiz session.

    Query params:
        count — number of questions (default 30, clamped to [1, 100]).
    """
    raw = request.query_params.get('count', 30)
    try:
        count = int(raw)
    except (TypeError, ValueError):
        return Response(
            {'detail': 'count must be an integer.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    count = max(1, min(count, 100))

    questions = Question.objects.order_by('?').prefetch_related('choices')[:count]
    serializer = QuestionSerializer(questions, many=True)
    return Response({
        'count': len(serializer.data),
        'questions': serializer.data,
    })


class QuestionDetailView(RetrieveAPIView):
    queryset = Question.objects.prefetch_related('choices')
    serializer_class = QuestionSerializer


@api_view(['POST'])
def submit_answer(request, question_id):
    """Validate an answer and return feedback with the picked choice's explanation."""
    request_ser = AnswerRequestSerializer(data=request.data)
    request_ser.is_valid(raise_exception=True)
    choice_id = request_ser.validated_data['choice_id']

    question = get_object_or_404(Question, pk=question_id)
    try:
        picked = question.choices.get(pk=choice_id)
    except Choice.DoesNotExist:
        return Response(
            {'detail': 'This choice does not belong to the given question.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    correct_choice = question.choices.filter(is_correct=True).first()
    return Response({
        'is_correct': picked.is_correct,
        'correct_choice_id': correct_choice.id if correct_choice else None,
        'explanation': picked.explanation,
    })
