from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.db import OperationalError
from rest_framework.throttling import AnonRateThrottle

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def isolate_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.parametrize('choice_id', [None, True, False, 0, -1, 1.5, 1.0, '1', [], {}, 2**63])
def test_answer_rejects_ambiguous_or_out_of_range_ids(api_client, make_question, choice_id):
    q = make_question()
    response = api_client.post(f'/api/questions/{q.id}/answer/',
                               {'choice_id': choice_id}, format='json')
    assert response.status_code == 400
    assert 'correct_choice_id' not in response.json()


@pytest.mark.parametrize('question_id', [None, True, False, 0, -1, 1.5, 1.0, '1', [], {}, 2**63])
def test_grade_rejects_ambiguous_or_out_of_range_ids(api_client, question_id):
    response = api_client.post('/api/grade/', {'answers': [
        {'question_id': question_id, 'choice_id': None},
    ]}, format='json')
    assert response.status_code == 400


@pytest.mark.parametrize('body', [None, [], 'text', 1, {}, {'answers': None},
                                      {'answers': {}}, {'answers': [None]}, {'answers': [True]}])
def test_grade_rejects_malformed_bodies(api_client, body):
    import json
    response = api_client.generic('POST', '/api/grade/', json.dumps(body),
                                  content_type='application/json')
    assert response.status_code == 400
    assert 'results' not in response.json()
    assert response['Cache-Control'] == 'no-store'


def test_grade_rejects_duplicates_before_querying(api_client, make_question, django_assert_num_queries):
    q = make_question()
    picked = q.choices.get(is_correct=True)
    with django_assert_num_queries(0):
        response = api_client.post('/api/grade/', {'answers': [
            {'question_id': q.id, 'choice_id': picked.id},
            {'question_id': q.id, 'choice_id': None},
        ]}, format='json')
    assert response.status_code == 400
    assert 'only once' in str(response.json())
    assert 'results' not in response.json()


def test_grade_rejects_excessive_items(api_client):
    response = api_client.post('/api/grade/', {'answers': [
        {'question_id': i, 'choice_id': None} for i in range(1, 102)
    ]}, format='json')
    assert response.status_code == 400


def test_grade_preserves_order_and_omitted_choice(api_client, make_question, django_assert_num_queries):
    q1, q2 = make_question(), make_question()
    picked = q2.choices.get(is_correct=True)
    body = {'answers': [{'question_id': q2.id, 'choice_id': picked.id},
                        {'question_id': q1.id}]}
    with django_assert_num_queries(2):
        response = api_client.post('/api/grade/', body, format='json')
    assert response.status_code == 200
    assert response.json()['score'] == 1
    assert [r['question_id'] for r in response.json()['results']] == [q2.id, q1.id]
    assert response.json()['results'][1]['choice_id'] is None
    # The stateless public grading operation can safely be retried.
    assert api_client.post('/api/grade/', body, format='json').json() == response.json()


def test_read_endpoints_never_leak_answers(api_client, question_bank):
    from quiz.models import Question
    forbidden = {'is_correct', 'correct_choice_id', 'correct_explanation', 'explanation', 'answer'}

    def inspect(value):
        if isinstance(value, dict):
            assert forbidden.isdisjoint(value)
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)

    for path in ['/api/quiz-set/?count=100', '/api/stats/'] + [
        f'/api/questions/{q.id}/' for q in Question.objects.all()
    ]:
        response = api_client.get(path)
        assert response.status_code == 200
        assert response['Cache-Control'] == 'no-store'
        inspect(response.json())


def test_stats_uses_one_grouped_query(api_client, question_bank, django_assert_num_queries):
    with django_assert_num_queries(1):
        assert api_client.get('/api/stats/').status_code == 200


def test_live_needs_no_database_and_readiness_handles_outage(api_client, django_assert_num_queries):
    with django_assert_num_queries(0):
        assert api_client.get('/api/live/').json() == {'status': 'ok'}
    with patch('quiz.views.connection.cursor', side_effect=OperationalError('SECRET_CANARY')):
        response = api_client.get('/api/health/')
    assert response.status_code == 503
    assert response.json() == {'status': 'error', 'database': 'down'}
    assert 'SECRET_CANARY' not in response.content.decode()


def test_forwarded_prefix_cannot_bypass_throttle(api_client, monkeypatch, question_bank):
    monkeypatch.setattr(AnonRateThrottle, 'THROTTLE_RATES', {'anon': '1/min'})
    headers = {'REMOTE_ADDR': '172.21.0.1', 'HTTP_X_FORWARDED_FOR': 'fake1, 192.0.2.10'}
    assert api_client.get('/api/stats/', **headers).status_code == 200
    headers['HTTP_X_FORWARDED_FOR'] = 'fake2, 192.0.2.10'
    response = api_client.get('/api/stats/', **headers)
    assert response.status_code == 429
    assert int(response['Retry-After']) > 0
    headers['HTTP_X_FORWARDED_FOR'] = '192.0.2.11'
    assert api_client.get('/api/stats/', **headers).status_code == 200


def test_api_body_size_is_bounded(api_client):
    response = api_client.generic('POST', '/api/grade/', 'x' * (64 * 1024 + 1),
                                  content_type='application/json')
    assert response.status_code == 413
    assert response.json() == {'detail': 'Request body is too large.'}
    assert response['Cache-Control'] == 'no-store'


def test_invalid_json_has_no_feedback(api_client):
    response = api_client.generic('POST', '/api/grade/', '{bad', content_type='application/json')
    assert response.status_code == 400
    assert 'results' not in response.json()


def test_saved_drill_fetches_only_requested_public_questions(api_client, make_question):
    q1, q2, q3 = make_question(), make_question(), make_question()
    response = api_client.get(f'/api/quiz-set/?ids={q1.id},{q3.id}&count=50')
    assert response.status_code == 200
    assert {q['id'] for q in response.json()['questions']} == {q1.id, q3.id}
    assert q2.id not in {q['id'] for q in response.json()['questions']}


@pytest.mark.parametrize('ids', ['', '0', '-1', '1,1', 'true', '1.0', '9223372036854775808',
                                     ','.join(str(i) for i in range(1, 102))])
def test_saved_drill_rejects_invalid_id_filter(api_client, ids):
    response = api_client.get('/api/quiz-set/', {'ids': ids})
    assert response.status_code == 400
    assert 'questions' not in response.json()

@pytest.mark.parametrize('correct_count', [0, 2])
def test_invalid_answer_key_fails_without_disclosing_feedback(api_client, make_question, correct_count):
    q = make_question()
    q.choices.update(is_correct=False)
    for c in q.choices.all()[:correct_count]:
        c.is_correct = True
        c.save()
    choice_id = q.choices.first().id
    for path, body in [(f'/api/questions/{q.id}/answer/', {'choice_id': choice_id}),
                       ('/api/grade/', {'answers': [{'question_id': q.id, 'choice_id': choice_id}]})]:
        response = api_client.post(path, body, format='json')
        assert response.status_code == 503
        assert set(response.json()) == {'detail'}
