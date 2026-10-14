import importlib.util
from copy import deepcopy
from datetime import datetime, timezone
import json
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
SHELL_CSP = (
    "default-src 'self'; base-uri 'self'; object-src 'none'; "
    "frame-ancestors 'none'; frame-src https://pcep-runner.micutu.com; "
    "form-action 'self'; img-src 'self' data:; font-src 'self'; "
    "manifest-src 'self'; worker-src 'self'; "
    "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'"
)
ANALYTICS_INTEGRITY = f"sha384-{'A' * 64}"


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


def test_shell_csp_is_exact_and_delegates_python_to_the_isolated_runner_origin():
    headers = {
        **SHARED_HEADERS,
        'content-type': 'text/html',
        'cache-control': 'no-cache, no-store',
        'content-security-policy': SHELL_CSP,
    }
    body = b'''<meta name="pcep-release" content="abc123def456">
    <link rel="stylesheet" href="/assets/index-abc12345.css">
    <script type="module" src="/assets/index-abc12345.js"></script>
    <template id="pcep-analytics-config" data-consent="required"
      data-src="/u/script.js"
      data-integrity="sha384-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
      data-website-id="b37781f1-2c12-4d98-88f7-48cf10f000fd"
      data-domains="pcep.micutu.com"></template>
    <div id="root"></div>'''
    assert smoke.check_shell(response(headers, body)) == (
        ['/assets/index-abc12345.js', '/assets/index-abc12345.css'],
        'abc123def456',
        ANALYTICS_INTEGRITY,
    )

    for directive in [
        "'wasm-unsafe-eval'",
        "'unsafe-eval'",
        'https://static.cloudflareinsights.com',
    ]:
        unsafe = response(
            {
                **headers,
                'content-security-policy': (
                    headers['content-security-policy'].replace(
                        "script-src 'self'", f"script-src 'self' {directive}"
                    )
                ),
            },
            body,
        )
        with pytest.raises(smoke.SmokeError, match='exact policy'):
            smoke.check_shell(unsafe)

    external_telemetry = response(
        {
            **headers,
            'content-security-policy': headers['content-security-policy'].replace(
                "connect-src 'self'",
                "connect-src 'self' https://cloudflareinsights.com",
            ),
        },
        body,
    )
    with pytest.raises(smoke.SmokeError, match='exact policy'):
        smoke.check_shell(external_telemetry)


def test_analytics_script_must_match_the_shell_integrity_and_set_no_cookie():
    import base64
    import hashlib

    body = b'reviewed analytics bytes'
    integrity = 'sha384-' + base64.b64encode(hashlib.sha384(body).digest()).decode()
    headers = {
        **SHARED_HEADERS,
        'content-type': 'application/javascript; charset=UTF-8',
        'content-security-policy': SHELL_CSP,
    }
    smoke.check_analytics_script(response(headers, body), integrity)

    for invalid in [
        response(headers, b'tampered analytics bytes'),
        response({**headers, 'set-cookie': 'tracker=1'}, body),
    ]:
        with pytest.raises(smoke.SmokeError):
            smoke.check_analytics_script(invalid, integrity)


def test_analytics_tag_requires_sri_and_privacy_attributes():
    valid = (
        '<template id="pcep-analytics-config" data-consent="required" '
        'data-src="/u/script.js" '
        f'data-integrity="{ANALYTICS_INTEGRITY}" '
        'data-website-id="b37781f1-2c12-4d98-88f7-48cf10f000fd" '
        'data-domains="pcep.micutu.com"></template>'
    ).encode()
    assert smoke.analytics_integrity(valid) == ANALYTICS_INTEGRITY

    with pytest.raises(smoke.SmokeError):
        smoke.analytics_integrity(valid.replace(b' data-consent="required"', b''))

    executable = valid + b'<script src="/u/script.js"></script>'
    with pytest.raises(smoke.SmokeError, match='before consent'):
        smoke.analytics_integrity(executable)


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


def test_retired_public_content_must_be_a_strict_cookie_free_404():
    headers = {
        **SHARED_HEADERS,
        'cache-control': 'no-store',
        'content-security-policy': "default-src 'none'; frame-ancestors 'none'",
        'x-request-id': 'a' * 32,
    }
    smoke.check_public_404(
        response(headers, b'Not found', status=404),
        'Retired content',
    )

    for invalid in [
        response({**headers, 'cache-control': 'public'}, status=404),
        response({**headers, 'set-cookie': 'session=secret'}, status=404),
        response(headers, status=200),
    ]:
        with pytest.raises(smoke.SmokeError):
            smoke.check_public_404(invalid, 'Retired content')


def test_legacy_static_cache_check_activates_at_the_documented_local_deadline():
    before = smoke.retired_content_paths(
        datetime(2026, 11, 11, 21, 59, tzinfo=timezone.utc)
    )
    at_deadline = smoke.retired_content_paths(
        datetime(2026, 11, 11, 22, 0, tzinfo=timezone.utc)
    )

    assert before == list(smoke.RETIRED_CONTENT_CANARY_PATHS)
    assert at_deadline == [
        *smoke.RETIRED_CONTENT_CANARY_PATHS,
        *smoke.RETIRED_CONTENT_LEGACY_PATHS,
    ]

    with pytest.raises(smoke.SmokeError, match='timezone'):
        smoke.retired_content_paths(datetime(2026, 11, 12))


def test_sensitive_route_canaries_cover_encoded_names_and_separators():
    assert '/%61dmin/login/' in smoke.ADMIN_DENIAL_PATHS
    assert '/admin%2flogin/' in smoke.ADMIN_DENIAL_PATHS
    assert '/%72unner.html' in smoke.LEARNER_ORIGIN_RUNNER_DENIAL_PATHS
    assert '/pyodide%2fVERSION' in smoke.LEARNER_ORIGIN_RUNNER_DENIAL_PATHS
    assert '/%73tatic/pcep-retired-origin-canary-20261013.txt' in (
        smoke.RETIRED_CONTENT_CANARY_PATHS
    )
    assert '/media%2fpcep-retired-origin-canary-20261013.txt' in (
        smoke.RETIRED_CONTENT_CANARY_PATHS
    )


def test_operations_health_requires_minimal_fresh_success_and_strict_headers():
    headers = {
        **SHARED_HEADERS,
        'cache-control': 'no-store',
        'content-type': 'application/json',
        'content-security-policy': "default-src 'none'; frame-ancestors 'none'",
        'x-request-id': 'a' * 32,
    }
    now = datetime(2026, 10, 13, 9, tzinfo=timezone.utc)
    payload = {
        'checked_at': '2026-10-13T08:00:00Z',
        'schema': 1,
        'status': 'ok',
    }
    assert smoke.check_operations_health(
        response(headers, json.dumps(payload).encode()), now=now
    ) == payload

    invalid_payloads = [
        {**payload, 'status': 'degraded'},
        {**payload, 'backup': 'private-detail'},
        {**payload, 'checked_at': '2026-10-13T06:59:59Z'},
        {**payload, 'checked_at': '2026-10-13T09:05:01Z'},
    ]
    for invalid in invalid_payloads:
        with pytest.raises(smoke.SmokeError):
            smoke.check_operations_health(
                response(headers, json.dumps(invalid).encode()), now=now
            )

    with pytest.raises(smoke.SmokeError, match='cacheable'):
        smoke.check_operations_health(
            response({**headers, 'cache-control': 'public'}, json.dumps(payload).encode()),
            now=now,
        )


def test_security_txt_requires_private_canonical_fresh_disclosure_metadata():
    headers = {
        **SHARED_HEADERS,
        'cache-control': 'no-cache, no-store, must-revalidate',
        'content-type': 'text/plain',
        'content-security-policy': "default-src 'none'; frame-ancestors 'none'",
        'x-request-id': 'a' * 32,
    }
    body = b'''Contact: https://github.com/Alexandru2984/PCEP_webApp/security/advisories/new
Expires: 2027-10-01T00:00:00Z
Preferred-Languages: en, ro
Canonical: https://pcep.micutu.com/.well-known/security.txt
Policy: https://github.com/Alexandru2984/PCEP_webApp/security/policy
'''
    now = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
    fields = smoke.check_security_txt(response(headers, body), now=now)
    assert fields['Contact'].endswith('/security/advisories/new')

    invalid_bodies = [
        body.replace(b'2027-10-01', b'2026-10-01'),
        body.replace(b'2027-10-01', b'2026-11-01'),
        body.replace(b'2027-10-01', b'2027-10-15'),
        body.replace(b'/security/advisories/new', b'/issues/new'),
        body.replace(
            b'Canonical: https://pcep.micutu.com/.well-known/security.txt\n',
            b'',
        ),
        body.replace(b'en, ro', b'ro, en'),
    ]
    for invalid in invalid_bodies:
        with pytest.raises(smoke.SmokeError):
            smoke.check_security_txt(response(headers, invalid), now=now)

    for invalid in [
        response({**headers, 'content-type': 'text/html'}, body),
        response({**headers, 'cache-control': 'public, max-age=86400'}, body),
        response({**headers, 'set-cookie': 'session=secret'}, body),
    ]:
        with pytest.raises(smoke.SmokeError):
            smoke.check_security_txt(invalid, now=now)


def test_tracked_security_txt_is_current_and_matches_the_public_contract():
    headers = {
        **SHARED_HEADERS,
        'cache-control': 'no-store',
        'content-type': 'text/plain',
        'content-security-policy': "default-src 'none'; frame-ancestors 'none'",
        'x-request-id': 'a' * 32,
    }
    source = (
        Path(__file__).resolve().parents[3]
        / 'frontend/public/.well-known/security.txt'
    ).read_bytes()
    smoke.check_security_txt(response(headers, source))


def test_runner_headers_forbid_credentials_and_cross_origin_resources():
    headers = {
        'strict-transport-security': 'max-age=31536000; includeSubDomains',
        'x-content-type-options': 'nosniff',
        'referrer-policy': 'no-referrer',
        'permissions-policy': (
            'camera=(), microphone=(), geolocation=(), payment=(), '
            'usb=(), serial=()'
        ),
        'cross-origin-resource-policy': 'same-origin',
        'origin-agent-cluster': '?1',
        'x-request-id': 'a' * 32,
        'cache-control': 'no-store',
    }
    smoke.check_runner_headers(response(headers), 'Runner')

    for invalid in [
        response({**headers, 'set-cookie': 'session=secret'}),
        response({**headers, 'x-frame-options': 'DENY'}),
        response({**headers, 'cross-origin-resource-policy': 'cross-origin'}),
    ]:
        with pytest.raises(smoke.SmokeError):
            smoke.check_runner_headers(invalid, 'Runner')


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
