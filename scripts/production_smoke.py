#!/usr/bin/env python3
"""Read-only public smoke checks for the deployed PCEP application."""

import argparse
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
import json
import re
import ssl
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
RELEASE_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
REQUEST_ID_PATTERN = re.compile(r'[0-9a-f]{32}')
ASSET_PATH_PATTERN = re.compile(
    r'/assets/[A-Za-z0-9._-]+-[A-Za-z0-9_-]{8}\.(?:css|js)'
)
FORBIDDEN_ANSWER_FIELDS = {
    'is_correct',
    'correct_choice',
    'correct_choice_id',
    'correct_explanation',
    'explanation',
}


class SmokeError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublicResponse:
    url: str
    status: int
    headers: dict[str, str]
    body: bytes


class ShellAssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stylesheets = []
        self.modules = []
        self.releases = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'link' and 'stylesheet' in (attributes.get('rel') or '').split():
            href = attributes.get('href') or ''
            if href.startswith('/assets/'):
                self.stylesheets.append(href)
        elif tag == 'script' and attributes.get('type') == 'module':
            src = attributes.get('src') or ''
            if src.startswith('/assets/'):
                self.modules.append(src)
        elif tag == 'meta' and attributes.get('name') == 'pcep-release':
            self.releases.append(attributes.get('content') or '')


def require(condition, message):
    if not condition:
        raise SmokeError(message)


def production_origin(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != 'https'
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip('/')
    ):
        raise SmokeError('The production base URL must be an HTTPS origin.')
    return value.rstrip('/')


def public_get(origin, path, attempts=3):
    url = f'{origin}/{path.lstrip("/")}'
    request = Request(
        url,
        headers={
            'Accept': 'application/json, text/html;q=0.9, */*;q=0.1',
            'Accept-Encoding': 'identity',
            'User-Agent': 'pcep-production-smoke/1',
        },
    )
    last_error = None
    for attempt in range(attempts):
        try:
            with urlopen(
                request,
                timeout=20,
                context=ssl.create_default_context(),
            ) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                require(
                    len(body) <= MAX_RESPONSE_BYTES,
                    f'{path} exceeded the response-size limit.',
                )
                require(response.status == 200, f'{path} returned HTTP {response.status}.')
                require(response.geturl() == url, f'{path} redirected unexpectedly.')
                return PublicResponse(
                    url=url,
                    status=response.status,
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=body,
                )
        except (HTTPError, URLError, TimeoutError, OSError, SmokeError) as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(attempt + 1)
    if isinstance(last_error, SmokeError):
        raise last_error
    raise SmokeError(f'{path} could not be reached after {attempts} attempts.') from last_error


def json_payload(response, label):
    require(
        response.headers.get('content-type', '').startswith('application/json'),
        f'{label} did not return JSON.',
    )
    try:
        return json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SmokeError(f'{label} returned malformed JSON.') from error


def csp_directives(value):
    directives = {}
    for raw in value.split(';'):
        parts = raw.strip().split()
        if parts:
            directives[parts[0]] = parts[1:]
    return directives


def check_shared_security_headers(response, label):
    require(
        response.headers.get('strict-transport-security', '').startswith('max-age='),
        f'{label} is missing HSTS.',
    )
    require(
        response.headers.get('x-content-type-options', '').lower() == 'nosniff',
        f'{label} is missing nosniff.',
    )
    require(
        response.headers.get('x-frame-options', '').upper() == 'DENY',
        f'{label} is not frame-denied.',
    )
    require(
        response.headers.get('referrer-policy') == 'strict-origin-when-cross-origin',
        f'{label} has an unexpected referrer policy.',
    )
    require(
        response.headers.get('permissions-policy')
        == 'camera=(), microphone=(), geolocation=(), payment=()',
        f'{label} has an unexpected permissions policy.',
    )
    require(
        response.headers.get('cross-origin-opener-policy') == 'same-origin',
        f'{label} has an unexpected opener policy.',
    )


def parse_shell(body):
    try:
        html = body.decode('utf-8')
    except UnicodeDecodeError as error:
        raise SmokeError('The application shell is not valid UTF-8.') from error
    parser = ShellAssetParser()
    parser.feed(html)
    return parser


def shell_assets(body):
    parser = parse_shell(body)
    require(parser.modules, 'The application shell has no module entry asset.')
    require(parser.stylesheets, 'The application shell has no stylesheet asset.')
    assets = parser.modules + parser.stylesheets
    require(len(assets) == len(set(assets)), 'The application shell repeats an entry asset.')
    require(
        all(ASSET_PATH_PATTERN.fullmatch(path) is not None for path in assets),
        'The application shell contains an invalid entry asset path.',
    )
    return assets


def shell_release(body):
    releases = parse_shell(body).releases
    require(len(releases) == 1, 'The application shell must expose one release marker.')
    release = releases[0]
    require(
        RELEASE_PATTERN.fullmatch(release) is not None
        and release not in {'development', 'unknown'},
        'The application shell has an invalid release marker.',
    )
    return release


def check_asset(response, path):
    label = f'Entry asset {path}'
    check_shared_security_headers(response, label)
    cache_control = response.headers.get('cache-control', '')
    require(
        all(value in cache_control for value in ('public', 'max-age=31536000', 'immutable')),
        f'{label} is missing immutable caching.',
    )
    content_type = response.headers.get('content-type', '').lower()
    expected_type = 'text/css' if path.endswith('.css') else 'javascript'
    require(expected_type in content_type, f'{label} has an invalid media type.')
    require(response.body, f'{label} is empty.')


def check_shell(response):
    require(
        response.headers.get('content-type', '').startswith('text/html'),
        'The application shell did not return HTML.',
    )
    require(b'id="root"' in response.body, 'The application root is missing.')
    require('no-store' in response.headers.get('cache-control', ''), 'The shell is cacheable.')
    check_shared_security_headers(response, 'The application shell')
    directives = csp_directives(response.headers.get('content-security-policy', ''))
    require("'self'" in directives.get('default-src', []), 'Shell CSP default-src drifted.')
    require("'none'" in directives.get('object-src', []), 'Shell CSP permits objects.')
    require("'none'" in directives.get('frame-ancestors', []), 'Shell CSP permits framing.')
    scripts = directives.get('script-src', [])
    require("'wasm-unsafe-eval'" in scripts, 'Shell CSP no longer permits the Pyodide runtime.')
    require("'unsafe-eval'" not in scripts, 'Shell CSP permits unsafe-eval.')
    require("'unsafe-inline'" not in scripts, 'Shell CSP permits inline scripts.')
    return shell_assets(response.body), shell_release(response.body)


def check_api_headers(response, releases, label):
    check_shared_security_headers(response, label)
    require('no-store' in response.headers.get('cache-control', ''), f'{label} is cacheable.')
    directives = csp_directives(response.headers.get('content-security-policy', ''))
    require(directives.get('default-src') == ["'none'"], f'{label} API CSP drifted.')
    require(
        directives.get('frame-ancestors') == ["'none'"],
        f'{label} API frame policy drifted.',
    )
    release = response.headers.get('x-pcep-release', '')
    require(
        RELEASE_PATTERN.fullmatch(release) is not None
        and release not in {'development', 'unknown'},
        f'{label} has an invalid release marker.',
    )
    request_id = response.headers.get('x-request-id', '')
    require(
        REQUEST_ID_PATTERN.fullmatch(request_id) is not None,
        f'{label} has an invalid request ID.',
    )
    releases.add(release)


def nested_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from nested_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_keys(child)


def check_answer_safe(value, label):
    leaked = FORBIDDEN_ANSWER_FIELDS.intersection(nested_keys(value))
    require(not leaked, f'{label} leaked pre-answer fields: {sorted(leaked)}.')


def check_public_question(question, label):
    question_fields = {
        'id',
        'text',
        'code_snippet',
        'difficulty',
        'module',
        'objective',
        'choices',
    }
    require(
        isinstance(question, dict) and set(question) == question_fields,
        f'{label} contains a malformed question.',
    )
    require(
        type(question['id']) is int and question['id'] > 0,
        f'{label} contains an invalid question ID.',
    )
    require(
        all(
            isinstance(question[field], str)
            for field in ('text', 'code_snippet', 'difficulty', 'module', 'objective')
        ),
        f'{label} contains malformed public question fields.',
    )
    require(
        isinstance(question['choices'], list) and len(question['choices']) == 4,
        f'{label} contains an invalid choice set.',
    )
    require(
        all(
            isinstance(choice, dict)
            and set(choice) == {'id', 'text'}
            and type(choice['id']) is int
            and choice['id'] > 0
            and isinstance(choice['text'], str)
            for choice in question['choices']
        ),
        f'{label} contains a malformed public choice.',
    )
    require(
        len({choice['id'] for choice in question['choices']}) == 4,
        f'{label} contains duplicate choice IDs.',
    )
    check_answer_safe(question, label)
    return question['id']


def check_question_set(payload, label, expected_ids=None):
    require(isinstance(payload, dict), f'{label} is not an object.')
    require(set(payload) == {'count', 'questions'}, f'{label} has unexpected fields.')
    questions = payload.get('questions')
    require(isinstance(questions, list), f'{label} questions are not a list.')
    require(
        type(payload.get('count')) is int and payload['count'] == len(questions),
        f'{label} count does not match.',
    )
    ids = [
        check_public_question(question, f'{label} question')
        for question in questions
    ]
    require(len(ids) == len(set(ids)), f'{label} contains duplicate question IDs.')
    if expected_ids is not None:
        require(ids == expected_ids, f'{label} did not preserve the requested ID order.')
    check_answer_safe(payload, label)
    return ids


def count_map(value):
    return (
        isinstance(value, dict)
        and value
        and all(
            isinstance(key, str) and type(count) is int and count >= 0
            for key, count in value.items()
        )
    )


def check_stats(payload):
    fields = {
        'total',
        'by_module',
        'by_difficulty',
        'by_objective',
        'objective_matrix',
        'matrix',
        'modules',
        'pass_threshold',
    }
    require(isinstance(payload, dict) and set(payload) == fields, 'Stats shape drifted.')
    total = payload['total']
    require(type(total) is int and 1 <= total <= 100_000, 'Stats total is invalid.')
    by_module = payload['by_module']
    by_difficulty = payload['by_difficulty']
    by_objective = payload['by_objective']
    require(count_map(by_module), 'Stats module totals are invalid.')
    require(count_map(by_difficulty), 'Stats difficulty totals are invalid.')
    require(count_map(by_objective), 'Stats objective totals are invalid.')
    require(sum(by_module.values()) == total, 'Stats module totals do not reconcile.')
    require(
        sum(by_difficulty.values()) == total,
        'Stats difficulty totals do not reconcile.',
    )
    require(
        sum(by_objective.values()) == total,
        'Stats objective totals do not reconcile.',
    )

    def check_matrix(value, row_totals, label):
        require(
            isinstance(value, dict) and set(value) == set(row_totals),
            f'{label} rows drifted.',
        )
        for key, row in value.items():
            require(
                count_map(row) and set(row) == set(by_difficulty),
                f'{label} row {key} drifted.',
            )
            require(
                sum(row.values()) == row_totals[key],
                f'{label} row {key} does not reconcile.',
            )
        for difficulty, expected in by_difficulty.items():
            require(
                sum(row[difficulty] for row in value.values()) == expected,
                f'{label} difficulty {difficulty} does not reconcile.',
            )

    check_matrix(payload['matrix'], by_module, 'Stats module matrix')
    check_matrix(payload['objective_matrix'], by_objective, 'Stats objective matrix')

    modules = payload['modules']
    require(
        isinstance(modules, list) and len(modules) == len(by_module),
        'Stats module summaries drifted.',
    )
    summaries = {}
    summary_fields = {'value', 'label', 'total', *by_difficulty}
    for summary in modules:
        require(
            isinstance(summary, dict)
            and set(summary) == summary_fields
            and summary['value'] in by_module
            and summary['value'] not in summaries
            and isinstance(summary['label'], str)
            and 1 <= len(summary['label']) <= 100,
            'Stats contains an invalid module summary.',
        )
        module = summary['value']
        require(
            summary['total'] == by_module[module]
            and all(
                summary[difficulty] == payload['matrix'][module][difficulty]
                for difficulty in by_difficulty
            ),
            f'Stats module summary {module} does not reconcile.',
        )
        summaries[module] = summary
    require(set(summaries) == set(by_module), 'Stats module summaries are incomplete.')
    require(
        type(payload['pass_threshold']) is int
        and 1 <= payload['pass_threshold'] <= 100,
        'Stats pass threshold is invalid.',
    )
    check_answer_safe(payload, 'Stats')
    return total


def check_search(payload):
    require(
        isinstance(payload, dict) and set(payload) == {'count', 'results'},
        'Search shape drifted.',
    )
    results = payload['results']
    require(
        isinstance(results, list)
        and type(payload['count']) is int
        and payload['count'] == len(results),
        'Search count does not match.',
    )
    fields = {'id', 'text', 'code_snippet', 'difficulty', 'module', 'objective'}
    for result in results:
        require(
            isinstance(result, dict)
            and set(result) == fields
            and type(result['id']) is int
            and result['id'] > 0
            and all(
                isinstance(result[field], str)
                for field in fields - {'id'}
            ),
            'Search contains a malformed preview.',
        )
    check_answer_safe(payload, 'Search')
    return results


def run(origin):
    releases = set()

    shell = public_get(origin, '/')
    assets, frontend_release = check_shell(shell)
    for asset_path in assets:
        check_asset(public_get(origin, asset_path), asset_path)

    live_response = public_get(origin, '/api/live/')
    check_api_headers(live_response, releases, 'Liveness')
    require(json_payload(live_response, 'Liveness') == {'status': 'ok'}, 'Liveness failed.')

    health_response = public_get(origin, '/api/health/')
    check_api_headers(health_response, releases, 'Readiness')
    require(
        json_payload(health_response, 'Readiness')
        == {'status': 'ok', 'database': 'up'},
        'Readiness failed.',
    )

    stats_response = public_get(origin, '/api/stats/')
    check_api_headers(stats_response, releases, 'Stats')
    stats = json_payload(stats_response, 'Stats')
    total = check_stats(stats)

    random_response = public_get(origin, '/api/quiz-set/?count=4')
    check_api_headers(random_response, releases, 'Public quiz set')
    random_payload = json_payload(random_response, 'Public quiz set')
    random_ids = check_question_set(random_payload, 'Public quiz set')
    require(len(random_ids) == 4, 'Public quiz set returned the wrong number of questions.')

    detail_response = public_get(origin, f'/api/questions/{random_ids[0]}/')
    check_api_headers(detail_response, releases, 'Question detail')
    detail = json_payload(detail_response, 'Question detail')
    require(
        check_public_question(detail, 'Question detail') == random_ids[0],
        'Question detail returned the wrong question.',
    )

    daily_response = public_get(origin, '/api/daily/')
    check_api_headers(daily_response, releases, 'Daily challenge')
    daily = json_payload(daily_response, 'Daily challenge')
    require(
        isinstance(daily, dict) and set(daily) == {'date', 'count', 'questions'},
        'Daily challenge shape drifted.',
    )
    require(
        daily['date'] == datetime.now(ZoneInfo('Europe/Bucharest')).date().isoformat(),
        'Daily challenge date drifted.',
    )
    daily_ids = check_question_set(
        {'count': daily['count'], 'questions': daily['questions']},
        'Daily challenge',
    )
    require(len(daily_ids) == 5, 'Daily challenge returned the wrong number of questions.')

    search_source = random_payload['questions'][0]
    search_match = re.search(r'[A-Za-z]{2,20}', search_source['text'])
    require(search_match is not None, 'Could not derive a safe public search probe.')
    search_query = urlencode({'q': search_match.group(), 'limit': 1})
    search_response = public_get(origin, f'/api/search/?{search_query}')
    check_api_headers(search_response, releases, 'Search')
    search_results = check_search(json_payload(search_response, 'Search'))
    require(len(search_results) == 1, 'Search returned the wrong number of previews.')

    requested_ids = list(reversed(random_ids))
    query = urlencode({'ids': ','.join(map(str, requested_ids)), 'count': 3})
    targeted_response = public_get(origin, f'/api/quiz-set/?{query}')
    check_api_headers(targeted_response, releases, 'Targeted quiz set')
    targeted_payload = json_payload(targeted_response, 'Targeted quiz set')
    targeted_ids = check_question_set(
        targeted_payload,
        'Targeted quiz set',
        expected_ids=requested_ids[:3],
    )

    worker = public_get(origin, '/sw.js')
    check_shared_security_headers(worker, 'Service worker')
    require('no-store' in worker.headers.get('cache-control', ''), 'Service worker is cacheable.')
    require(
        'javascript' in worker.headers.get('content-type', ''),
        'Service worker has an invalid media type.',
    )

    require(len(releases) == 1, 'Public API endpoints report different releases.')
    return {
        'backend_release': next(iter(releases)),
        'frontend_release': frontend_release,
        'questions': total,
        'targeted_order': targeted_ids,
        'assets': len(assets),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--base-url',
        default='https://pcep.micutu.com',
        help='Production HTTPS origin (default: %(default)s)',
    )
    args = parser.parse_args(argv)
    try:
        result = run(production_origin(args.base_url))
    except SmokeError as error:
        parser.exit(1, f'Production smoke failed: {error}\n')
    print(
        'Production smoke passed: '
        f'backend_release={result["backend_release"]} '
        f'frontend_release={result["frontend_release"]} '
        f'questions={result["questions"]} '
        f'assets={result["assets"]} '
        f'targeted_order={",".join(map(str, result["targeted_order"]))}'
    )


if __name__ == '__main__':
    main()
