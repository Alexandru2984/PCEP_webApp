import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'production_smoke',
    Path(__file__).resolve().parents[3] / 'scripts/production_smoke.py',
)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)

SHARED_HEADERS = {
    'strict-transport-security': 'max-age=31536000; includeSubDomains',
    'x-content-type-options': 'nosniff',
    'x-frame-options': 'DENY',
    'referrer-policy': 'strict-origin-when-cross-origin',
    'permissions-policy': 'camera=(), microphone=(), geolocation=(), payment=()',
    'cross-origin-opener-policy': 'same-origin',
}


def response(headers=None, body=b'', status=200):
    return smoke.PublicResponse(
        url='https://example.test/api/live/',
        status=status,
        headers=headers or {},
        body=body,
    )


def public_question(question_id):
    return {
        'id': question_id,
        'text': 'What is printed?',
        'code_snippet': 'print(1)',
        'difficulty': 'easy',
        'module': 'module1',
        'objective': '1.4',
        'choices': [
            {'id': question_id * 10 + index, 'text': str(index)}
            for index in range(1, 5)
        ],
    }


def stats_payload():
    return {
        'total': 3,
        'by_module': {'module1': 3},
        'by_difficulty': {'easy': 1, 'medium': 2},
        'by_objective': {'1.1': 1, '1.4': 2},
        'matrix': {'module1': {'easy': 1, 'medium': 2}},
        'objective_matrix': {
            '1.1': {'easy': 1, 'medium': 0},
            '1.4': {'easy': 0, 'medium': 2},
        },
        'modules': [
            {
                'value': 'module1',
                'label': 'Module 1',
                'total': 3,
                'easy': 1,
                'medium': 2,
            }
        ],
        'pass_threshold': 70,
    }


def test_question_set_requires_order_and_rejects_answer_metadata():
    payload = {
        'count': 2,
        'questions': [public_question(3), public_question(1)],
    }
    assert smoke.check_question_set(payload, 'Targeted', [3, 1]) == [3, 1]

    payload['questions'][1]['choices'][0]['is_correct'] = True
    with pytest.raises(smoke.SmokeError, match='pre-answer fields'):
        smoke.check_answer_safe(payload, 'Targeted')


def test_question_set_rejects_a_valid_but_wrong_order():
    payload = {
        'count': 2,
        'questions': [public_question(1), public_question(3)],
    }
    with pytest.raises(smoke.SmokeError, match='requested ID order'):
        smoke.check_question_set(payload, 'Targeted', [3, 1])


def test_stats_contract_reconciles_every_public_breakdown():
    payload = stats_payload()
    assert smoke.check_stats(payload) == 3

    invalid = deepcopy(payload)
    invalid['objective_matrix']['1.4']['medium'] = 1
    with pytest.raises(smoke.SmokeError, match='objective matrix row 1.4'):
        smoke.check_stats(invalid)


def test_search_contract_excludes_choices_and_answer_metadata():
    payload = {
        'count': 1,
        'results': [
            {
                key: value
                for key, value in public_question(1).items()
                if key != 'choices'
            }
        ],
    }
    assert smoke.check_search(payload) == payload['results']

    payload['results'][0]['choices'] = []
    with pytest.raises(smoke.SmokeError, match='malformed preview'):
        smoke.check_search(payload)


def test_question_detail_rejects_extra_answer_fields():
    question = public_question(4)
    assert smoke.check_public_question(question, 'Detail') == 4

    question['choices'][0]['explanation'] = 'leak'
    with pytest.raises(smoke.SmokeError, match='malformed public choice'):
        smoke.check_public_question(question, 'Detail')


def test_api_headers_require_release_request_id_no_store_and_strict_csp():
    valid = response({
        **SHARED_HEADERS,
        'cache-control': 'no-store',
        'content-security-policy': "default-src 'none'; frame-ancestors 'none'",
        'x-pcep-release': 'abc123def456',
        'x-request-id': 'a' * 32,
    })
    releases = set()
    smoke.check_api_headers(valid, releases, 'API')
    assert releases == {'abc123def456'}

    invalid = response({**valid.headers, 'cache-control': 'public, max-age=300'})
    with pytest.raises(smoke.SmokeError, match='cacheable'):
        smoke.check_api_headers(invalid, set(), 'API')


def test_shell_csp_keeps_pyodide_without_general_eval_or_inline_scripts():
    headers = {
        **SHARED_HEADERS,
        'content-type': 'text/html',
        'cache-control': 'no-cache, no-store',
        'content-security-policy': (
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'; "
            "script-src 'self' 'wasm-unsafe-eval'"
        ),
    }
    body = b'''<meta name="pcep-release" content="abc123def456">
    <link rel="stylesheet" href="/assets/index-abc12345.css">
    <script type="module" src="/assets/index-abc12345.js"></script>
    <div id="root"></div>'''
    assert smoke.check_shell(response(headers, body)) == (
        ['/assets/index-abc12345.js', '/assets/index-abc12345.css'],
        'abc123def456',
    )

    unsafe = response({
        **headers,
        'content-security-policy': headers['content-security-policy'] + " 'unsafe-eval'",
    }, body)
    with pytest.raises(smoke.SmokeError, match='unsafe-eval'):
        smoke.check_shell(unsafe)


def test_public_admin_must_be_a_strict_cookie_free_404():
    headers = {
        **SHARED_HEADERS,
        'cache-control': 'no-store',
        'content-security-policy': "default-src 'none'; frame-ancestors 'none'",
        'x-request-id': 'a' * 32,
    }
    smoke.check_admin_unavailable(response(headers, b'Not found', status=404))

    for invalid in [
        response(headers, b'Django administration', status=404),
        response({**headers, 'set-cookie': 'sessionid=secret'}, status=404),
        response(headers, status=200),
    ]:
        with pytest.raises(smoke.SmokeError):
            smoke.check_admin_unavailable(invalid)


def test_shell_assets_require_safe_hashed_asset_paths():
    body = b'''<script type="module" src="/assets/index-a1234567.js?stale=1"></script>
    <link rel="stylesheet" href="/assets/index-a1234567.css">'''
    with pytest.raises(smoke.SmokeError, match='invalid entry asset path'):
        smoke.shell_assets(body)


def test_shell_release_requires_one_production_marker():
    assert (
        smoke.shell_release(b'<meta name="pcep-release" content="abc123def456">')
        == 'abc123def456'
    )

    for body in [
        b'',
        b'<meta name="pcep-release" content="development">',
        b'<meta name="pcep-release" content="good"><meta name="pcep-release" content="other">',
    ]:
        with pytest.raises(smoke.SmokeError, match='release marker'):
            smoke.shell_release(body)


def test_entry_assets_require_security_headers_cache_policy_and_media_type():
    headers = {
        **SHARED_HEADERS,
        'cache-control': 'public, max-age=31536000, immutable',
        'content-type': 'application/javascript',
    }
    smoke.check_asset(response(headers, b'export {};'), '/assets/index-a1234567.js')

    invalid = response({**headers, 'cache-control': 'no-store'}, b'export {};')
    with pytest.raises(smoke.SmokeError, match='immutable caching'):
        smoke.check_asset(invalid, '/assets/index-a1234567.js')


@pytest.mark.parametrize(
    'value',
    ['http://pcep.micutu.com', 'https://user@example.test', 'https://example.test/path'],
)
def test_production_origin_rejects_insecure_or_non_origin_urls(value):
    with pytest.raises(smoke.SmokeError):
        smoke.production_origin(value)
