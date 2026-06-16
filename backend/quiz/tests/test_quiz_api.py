import pytest

from quiz.models import Question


pytestmark = pytest.mark.django_db


def test_health_endpoint_reports_ok(api_client):
    resp = api_client.get('/api/health/')
    assert resp.status_code == 200
    assert resp.json() == {'status': 'ok', 'database': 'up'}


def test_quiz_set_returns_requested_count(api_client, question_bank):
    resp = api_client.get('/api/quiz-set/?count=3')
    assert resp.status_code == 200
    body = resp.json()
    assert body['count'] == 3
    assert len(body['questions']) == 3
    # Public serializer must NOT leak is_correct / explanation on choices.
    for choice in body['questions'][0]['choices']:
        assert set(choice.keys()) == {'id', 'text'}


def test_quiz_set_clamps_count_upper_bound(api_client, question_bank):
    resp = api_client.get('/api/quiz-set/?count=9999')
    assert resp.status_code == 200
    # Only 5 in fixture — clamp doesn't invent questions.
    assert resp.json()['count'] == 5


def test_quiz_set_rejects_non_integer_count(api_client, question_bank):
    resp = api_client.get('/api/quiz-set/?count=abc')
    assert resp.status_code == 400


def test_quiz_set_filters_by_module(api_client, question_bank):
    resp = api_client.get('/api/quiz-set/?module=module1&count=20')
    assert resp.status_code == 200
    modules = {q['module'] for q in resp.json()['questions']}
    assert modules == {'module1'}


def test_quiz_set_filters_by_difficulty(api_client, question_bank):
    resp = api_client.get('/api/quiz-set/?difficulty=hard&count=20')
    assert resp.status_code == 200
    diffs = {q['difficulty'] for q in resp.json()['questions']}
    assert diffs == {'hard'}


def test_quiz_set_rejects_bogus_module(api_client, question_bank):
    resp = api_client.get('/api/quiz-set/?module=module99')
    assert resp.status_code == 400


def test_submit_correct_answer(api_client, make_question):
    q = make_question(correct_index=2)
    correct = q.choices.get(is_correct=True)
    resp = api_client.post(
        f'/api/questions/{q.id}/answer/',
        data={'choice_id': correct.id},
        format='json',
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body['is_correct'] is True
    assert body['correct_choice_id'] == correct.id
    assert 'choice 2' in body['explanation'].lower()


def test_submit_wrong_answer_returns_its_own_explanation(api_client, make_question):
    q = make_question(correct_index=0)
    wrong = q.choices.filter(is_correct=False).first()
    correct = q.choices.get(is_correct=True)
    resp = api_client.post(
        f'/api/questions/{q.id}/answer/',
        data={'choice_id': wrong.id},
        format='json',
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body['is_correct'] is False
    # correct_choice_id always points at the right answer, not the picked one.
    assert body['correct_choice_id'] == correct.id
    # Explanation is the picked choice's — so the user learns WHY their pick was wrong.
    assert body['explanation'] == wrong.explanation


def test_submit_rejects_choice_from_another_question(api_client, make_question):
    q1 = make_question()
    q2 = make_question()
    foreign = q2.choices.first()
    resp = api_client.post(
        f'/api/questions/{q1.id}/answer/',
        data={'choice_id': foreign.id},
        format='json',
    )
    assert resp.status_code == 400


def test_submit_404_on_unknown_question(api_client, make_question):
    q = make_question()
    choice = q.choices.first()
    resp = api_client.post(
        '/api/questions/999999/answer/',
        data={'choice_id': choice.id},
        format='json',
    )
    assert resp.status_code == 404


def test_submit_validates_payload(api_client, make_question):
    q = make_question()
    resp = api_client.post(
        f'/api/questions/{q.id}/answer/',
        data={},
        format='json',
    )
    assert resp.status_code == 400


def test_grade_scores_a_batch(api_client, make_question):
    q1 = make_question(correct_index=0)  # answered correctly
    q2 = make_question(correct_index=1)  # answered wrong
    q3 = make_question(correct_index=2)  # left blank
    correct1 = q1.choices.get(is_correct=True)
    wrong2 = q2.choices.filter(is_correct=False).first()

    resp = api_client.post(
        '/api/grade/',
        data={
            'answers': [
                {'question_id': q1.id, 'choice_id': correct1.id},
                {'question_id': q2.id, 'choice_id': wrong2.id},
                {'question_id': q3.id, 'choice_id': None},
            ]
        },
        format='json',
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body['count'] == 3
    assert body['score'] == 1
    by_q = {r['question_id']: r for r in body['results']}
    assert by_q[q1.id]['is_correct'] is True
    assert by_q[q2.id]['is_correct'] is False
    # Skipped question still reveals the correct choice for review.
    assert by_q[q3.id]['is_correct'] is False
    assert by_q[q3.id]['correct_choice_id'] == q3.choices.get(is_correct=True).id


def test_grade_rejects_empty_answers(api_client):
    resp = api_client.post('/api/grade/', data={'answers': []}, format='json')
    assert resp.status_code == 400


def test_grade_rejects_unknown_question(api_client, make_question):
    q = make_question()
    resp = api_client.post(
        '/api/grade/',
        data={'answers': [{'question_id': 999999, 'choice_id': q.choices.first().id}]},
        format='json',
    )
    assert resp.status_code == 400


def test_grade_rejects_foreign_choice(api_client, make_question):
    q1 = make_question()
    q2 = make_question()
    foreign = q2.choices.first()
    resp = api_client.post(
        '/api/grade/',
        data={'answers': [{'question_id': q1.id, 'choice_id': foreign.id}]},
        format='json',
    )
    assert resp.status_code == 400
