from django.db import connection
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from .models import Choice, Question
from .serializers import (
    AnswerRequestSerializer,
    GradeRequestSerializer,
    QuestionSerializer,
)


VALID_DIFFICULTIES = {d for d, _ in Question.DIFFICULTY_CHOICES}
VALID_MODULES = {m for m, _ in Question.MODULE_CHOICES}
PASS_THRESHOLD = 70


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([])  # liveness/readiness probes must not be rate-limited
def health(request):
    """Liveness/readiness probe: 200 only when the database is reachable."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception:
        return Response({'status': 'error', 'database': 'down'},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({'status': 'ok', 'database': 'up'})


@api_view(['GET'])
def stats(request):
    """Return aggregate question-bank coverage without exposing answers."""
    modules = dict(Question.MODULE_CHOICES)
    difficulties = dict(Question.DIFFICULTY_CHOICES)
    module_counts = {key: 0 for key in modules}
    difficulty_counts = {key: 0 for key in difficulties}
    matrix = {
        module: {difficulty: 0 for difficulty in difficulties}
        for module in modules
    }

    for row in Question.objects.values('module').annotate(total=Count('id')):
        module_counts[row['module']] = row['total']

    for row in Question.objects.values('difficulty').annotate(total=Count('id')):
        difficulty_counts[row['difficulty']] = row['total']

    rows = (
        Question.objects.values('module', 'difficulty')
        .annotate(total=Count('id'))
        .order_by()
    )
    for row in rows:
        matrix[row['module']][row['difficulty']] = row['total']

    module_summaries = []
    for value, label in Question.MODULE_CHOICES:
        summary = {
            'value': value,
            'label': label,
            'total': module_counts[value],
        }
        summary.update(matrix[value])
        module_summaries.append(summary)

    return Response({
        'total': Question.objects.count(),
        'by_module': module_counts,
        'by_difficulty': difficulty_counts,
        'matrix': matrix,
        'modules': module_summaries,
        'pass_threshold': PASS_THRESHOLD,
    })


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
        # The picked choice's explanation — for a wrong pick, WHY it is wrong.
        'explanation': picked.explanation,
        # The correct choice's explanation — the underlying concept. Lets the UI
        # always show why the right answer is right, even on a wrong/blank pick.
        'correct_explanation': correct_choice.explanation if correct_choice else '',
    })


@api_view(['POST'])
@throttle_classes([SubmitAnswerThrottle])
def grade(request):
    """Grade a whole batch of answers in one request (used by exam mode).

    Body: {"answers": [{"question_id": N, "choice_id": M | null}, ...]}
    Returns one result per answer with correctness, the correct choice id and
    the picked choice's explanation. A null/foreign choice_id counts as wrong.
    """
    request_ser = GradeRequestSerializer(data=request.data)
    request_ser.is_valid(raise_exception=True)
    answers = request_ser.validated_data['answers']

    question_ids = {a['question_id'] for a in answers}
    questions = (
        Question.objects.filter(id__in=question_ids).prefetch_related('choices')
    )
    question_map = {q.id: q for q in questions}

    results = []
    for answer in answers:
        question = question_map.get(answer['question_id'])
        if question is None:
            return Response(
                {'detail': f"Unknown question id {answer['question_id']}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        choices = {c.id: c for c in question.choices.all()}
        picked = choices.get(answer['choice_id'])
        if answer['choice_id'] is not None and picked is None:
            return Response(
                {'detail': f"Choice {answer['choice_id']} does not belong to "
                           f"question {question.id}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        correct = next((c for c in choices.values() if c.is_correct), None)
        results.append({
            'question_id': question.id,
            'choice_id': answer['choice_id'],
            'is_correct': bool(picked and picked.is_correct),
            'correct_choice_id': correct.id if correct else None,
            # Picked choice's explanation ('' when the question was skipped),
            # plus the correct choice's explanation so review always shows why
            # the right answer is right.
            'explanation': picked.explanation if picked else '',
            'correct_explanation': correct.explanation if correct else '',
        })

    score = sum(1 for r in results if r['is_correct'])
    return Response({'count': len(results), 'score': score, 'results': results})
