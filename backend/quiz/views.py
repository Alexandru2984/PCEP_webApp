from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from .models import Choice, Question
from .serializers import AnswerRequestSerializer, QuestionSerializer


VALID_DIFFICULTIES = {d for d, _ in Question.DIFFICULTY_CHOICES}
VALID_MODULES = {m for m, _ in Question.MODULE_CHOICES}


class SubmitAnswerThrottle(AnonRateThrottle):
    scope = 'submit_answer'


@api_view(['GET'])
def quiz_set(request):
    """Return a randomized set of questions for a quiz session.

    Query params:
        count      — number of questions (default 30, clamped to [1, 100]).
        difficulty — optional: easy | medium | hard.
        module     — optional: module1 | module2 | module3 | module4.
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

    qs = Question.objects.all()

    difficulty = request.query_params.get('difficulty')
    if difficulty:
        if difficulty not in VALID_DIFFICULTIES:
            return Response(
                {'detail': f'difficulty must be one of {sorted(VALID_DIFFICULTIES)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = qs.filter(difficulty=difficulty)

    module = request.query_params.get('module')
    if module:
        if module not in VALID_MODULES:
            return Response(
                {'detail': f'module must be one of {sorted(VALID_MODULES)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = qs.filter(module=module)

    questions = qs.order_by('?').prefetch_related('choices')[:count]
    serializer = QuestionSerializer(questions, many=True)
    return Response({
        'count': len(serializer.data),
        'questions': serializer.data,
    })


class QuestionDetailView(RetrieveAPIView):
    queryset = Question.objects.prefetch_related('choices')
    serializer_class = QuestionSerializer


@api_view(['POST'])
@throttle_classes([SubmitAnswerThrottle])
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
