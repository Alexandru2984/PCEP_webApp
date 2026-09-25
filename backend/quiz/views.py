import hmac
import random

from django.conf import settings
from django.db import connection, DatabaseError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from .models import Question
from .serializers import (
    AnswerRequestSerializer,
    GradeRequestSerializer,
    QuestionSearchSerializer,
    QuestionSerializer,
)


VALID_DIFFICULTIES = {d for d, _ in Question.DIFFICULTY_CHOICES}
VALID_MODULES = {m for m, _ in Question.MODULE_CHOICES}
PASS_THRESHOLD = 70
SEARCH_QUERY_MIN_LENGTH = 2
SEARCH_QUERY_MAX_LENGTH = 80
SEARCH_RESULT_LIMIT = 20
DAILY_CHALLENGE_SIZE = 5
PCEP_30_02_PRESET = 'pcep-30-02'
PCEP_30_02_DISTRIBUTION = {
    Question.MODULE_1: 7,
    Question.MODULE_2: 8,
    Question.MODULE_3: 7,
    Question.MODULE_4: 8,
}


def _daily_question_ids(rows, challenge_date):
    """Choose a stable, syllabus-balanced set without loading answer data."""
    key = settings.SECRET_KEY.encode('utf-8')

    def rank(row):
        message = f'pcep-daily:{challenge_date}:{row["id"]}'.encode('ascii')
        return hmac.digest(key, message, 'sha256'), row['id']

    ranked = sorted(rows, key=rank)
    first_by_module = {}
    for row in ranked:
        first_by_module.setdefault(row['module'], row['id'])

    selected = set(first_by_module.values())
    for row in ranked:
        if len(selected) >= DAILY_CHALLENGE_SIZE:
            break
        selected.add(row['id'])
    return [row['id'] for row in ranked if row['id'] in selected][:DAILY_CHALLENGE_SIZE]


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([])
def live(request):
    """Process liveness, deliberately independent of database availability."""
    return Response({'status': 'ok'})


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([])  # liveness/readiness probes must not be rate-limited
def health(request):
    """Readiness probe, preserving the existing monitoring response contract."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except DatabaseError:
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

    rows = (
        Question.objects.values('module', 'difficulty')
        .annotate(total=Count('id'))
        .order_by()
    )
    for row in rows:
        module_counts[row['module']] += row['total']
        difficulty_counts[row['difficulty']] += row['total']
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
        'total': sum(module_counts.values()),
        'by_module': module_counts,
        'by_difficulty': difficulty_counts,
        'matrix': matrix,
        'modules': module_summaries,
        'pass_threshold': PASS_THRESHOLD,
    })


@api_view(['GET'])
def search_questions(request):
    """Find question previews without exposing choices or answer metadata."""
    query = request.query_params.get('q', '').strip()
    if not SEARCH_QUERY_MIN_LENGTH <= len(query) <= SEARCH_QUERY_MAX_LENGTH:
        return Response(
            {'detail': 'q must contain 2 to 80 characters.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in query):
        return Response(
            {'detail': 'q must not contain control characters.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    raw_limit = request.query_params.get('limit', SEARCH_RESULT_LIMIT)
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return Response(
            {'detail': 'limit must be an integer.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not 1 <= limit <= SEARCH_RESULT_LIMIT:
        return Response(
            {'detail': f'limit must be between 1 and {SEARCH_RESULT_LIMIT}.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    questions = Question.objects.filter(
        Q(text__icontains=query) | Q(code_snippet__icontains=query)
    )
    module = request.query_params.get('module')
    if module:
        if module not in VALID_MODULES:
            return Response(
                {'detail': f'module must be one of {sorted(VALID_MODULES)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        questions = questions.filter(module=module)
    difficulty = request.query_params.get('difficulty')
    if difficulty:
        if difficulty not in VALID_DIFFICULTIES:
            return Response(
                {'detail': f'difficulty must be one of {sorted(VALID_DIFFICULTIES)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        questions = questions.filter(difficulty=difficulty)

    data = QuestionSearchSerializer(questions.order_by('id')[:limit], many=True).data
    return Response({'count': len(data), 'results': data})


@api_view(['GET'])
def daily_challenge(request):
    """Return the same balanced public question set throughout the local day."""
    challenge_date = timezone.localdate().isoformat()
    rows = list(Question.objects.values('id', 'module'))
    selected_ids = _daily_question_ids(rows, challenge_date)
    position = {question_id: index for index, question_id in enumerate(selected_ids)}
    questions = list(
        Question.objects.filter(id__in=selected_ids).prefetch_related('choices')
    )
    questions.sort(key=lambda question: position[question.id])
    data = QuestionSerializer(questions, many=True).data
    return Response({
        'date': challenge_date,
        'count': len(data),
        'questions': data,
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

    preset = request.query_params.get('preset')
    if preset is not None:
        if preset != PCEP_30_02_PRESET:
            return Response(
                {'detail': f'preset must be {PCEP_30_02_PRESET}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        preset_count = sum(PCEP_30_02_DISTRIBUTION.values())
        conflicting = [
            name for name in ('ids', 'module', 'difficulty')
            if name in request.query_params
        ]
        if count != preset_count or conflicting:
            return Response(
                {
                    'detail': (
                        f'{PCEP_30_02_PRESET} requires count={preset_count} '
                        'without ids, module or difficulty filters.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        selected_ids = []
        for module_value, module_count in PCEP_30_02_DISTRIBUTION.items():
            module_ids = list(
                qs.filter(module=module_value)
                .order_by('?')
                .values_list('id', flat=True)[:module_count]
            )
            if len(module_ids) != module_count:
                return Response(
                    {'detail': 'The full mock preset is temporarily unavailable.'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            selected_ids.extend(module_ids)

        random.shuffle(selected_ids)
        position = {
            question_id: index for index, question_id in enumerate(selected_ids)
        }
        questions = list(
            qs.filter(id__in=selected_ids).prefetch_related('choices')
        )
        if len(questions) != preset_count:
            return Response(
                {'detail': 'The full mock preset is temporarily unavailable.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        questions.sort(key=lambda question: position[question.id])
        serializer = QuestionSerializer(questions, many=True)
        return Response({
            'count': len(serializer.data),
            'preset': PCEP_30_02_PRESET,
            'questions': serializer.data,
        })

    ids = request.query_params.get('ids')
    if ids is not None:
        parts = ids.split(',')
        if len(parts) > 100 or any(not p.isascii() or not p.isdigit() or len(p) > 19 for p in parts):
            return Response({'detail': 'ids must contain 1 to 100 positive integers.'},
                            status=status.HTTP_400_BAD_REQUEST)
        selected_ids = [int(p) for p in parts]
        if any(i < 1 or i > 2**63 - 1 for i in selected_ids) or len(set(selected_ids)) != len(selected_ids):
            return Response({'detail': 'ids must be unique positive 64-bit integers.'},
                            status=status.HTTP_400_BAD_REQUEST)
        qs = qs.filter(id__in=selected_ids)

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

    question = get_object_or_404(Question.objects.prefetch_related('choices'), pk=question_id)
    choices = list(question.choices.all())
    picked = next((c for c in choices if c.id == choice_id), None)
    if picked is None:
        return Response(
            {'detail': 'This choice does not belong to the given question.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    correct_choices = [c for c in choices if c.is_correct]
    if len(correct_choices) != 1:
        return Response({'detail': 'This question is temporarily unavailable.'},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE)
    correct_choice = correct_choices[0]
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
    the picked choice's explanation. Null/omitted choices count as wrong;
    duplicate questions, unknown questions and foreign choices are rejected.
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
        correct_choices = [c for c in choices.values() if c.is_correct]
        if len(correct_choices) != 1:
            return Response({'detail': 'A question is temporarily unavailable.'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        correct = correct_choices[0]
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
