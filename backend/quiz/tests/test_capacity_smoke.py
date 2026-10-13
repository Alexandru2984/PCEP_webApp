import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    'capacity_smoke', PROJECT_ROOT / 'scripts/capacity_smoke.py'
)
capacity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capacity)


@pytest.mark.parametrize(
    'origin',
    [
        'http://127.0.0.1:8001',
        'http://127.1.2.3:8001/',
        'http://localhost:8001',
        'https://[::1]:8443',
    ],
)
def test_capacity_origin_accepts_only_explicit_loopback_origins(origin):
    assert capacity.loopback_origin(origin) == origin.rstrip('/')


@pytest.mark.parametrize(
    'origin',
    [
        'https://pcep.micutu.com:443',
        'http://10.0.0.2:8001',
        'http://127.0.0.1',
        'http://127.0.0.1:0',
        'http://user@127.0.0.1:8001',
        'http://127.0.0.1:8001/api/',
        'file:///tmp/socket:1',
    ],
)
def test_capacity_origin_refuses_remote_ambiguous_or_scoped_targets(origin):
    with pytest.raises(capacity.CapacityError):
        capacity.loopback_origin(origin)


@pytest.mark.parametrize(
    'value,label,minimum,maximum',
    [
        (61, 'duration', 1, capacity.MAX_DURATION_SECONDS),
        (51, 'rate', 1, capacity.MAX_RATE_PER_SECOND),
        (21, 'concurrency', 1, capacity.MAX_CONCURRENCY),
        (11, 'timeout', 1, capacity.MAX_TIMEOUT_SECONDS),
    ],
)
def test_capacity_bounds_cannot_exceed_safety_ceiling(value, label, minimum, maximum):
    with pytest.raises(capacity.CapacityError, match=label):
        capacity.bounded_int(
            value,
            label=label,
            minimum=minimum,
            maximum=maximum,
        )


def test_fetch_uses_one_read_only_request_and_discards_response_content():
    observed = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            observed['method'] = self.command
            observed['path'] = self.path
            observed['host'] = self.headers.get('Host')
            observed['forwarded_proto'] = self.headers.get('X-Forwarded-Proto')
            body = json.dumps({'private-looking': 'discard me'}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = capacity.fetch(
            f'http://127.0.0.1:{server.server_port}',
            '/api/quiz-set/?count=4',
            'pcep.micutu.com',
            2,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == 200
    assert result.error is None
    assert result.response_bytes > 0
    assert observed == {
        'method': 'GET',
        'path': '/api/quiz-set/?count=4',
        'host': 'pcep.micutu.com',
        'forwarded_proto': 'https',
    }
    assert 'private-looking' not in repr(result)


def test_fetch_refuses_redirects_before_they_can_leave_loopback():
    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header('Location', 'https://example.com/must-not-be-requested')
            self.end_headers()

        def log_message(self, _format, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), RedirectHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = capacity.fetch(
            f'http://127.0.0.1:{server.server_port}',
            '/api/live/',
            'pcep.micutu.com',
            2,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.status == 302
    assert result.error == 'http_status'


def test_capacity_opener_disables_environment_proxies(monkeypatch):
    original = capacity.build_opener
    supplied_handlers = []

    def capture_handlers(*handlers):
        supplied_handlers.extend(handlers)
        return original(*handlers)

    monkeypatch.setattr(capacity, 'build_opener', capture_handlers)
    capacity.local_opener()

    proxy_handlers = [
        handler
        for handler in supplied_handlers
        if isinstance(handler, capacity.ProxyHandler)
    ]
    assert len(proxy_handlers) == 1
    assert proxy_handlers[0].proxies == {}


def test_summary_is_aggregate_only_and_thresholds_fail_closed():
    results = [
        capacity.ProbeResult('/api/live/', 200, 10.0, 15),
        capacity.ProbeResult('/api/stats/', 503, 900.0, 0, 'http_status'),
    ]
    summary = capacity.summarize(
        results,
        requested_rate=10,
        duration=1,
        elapsed=1,
    )

    assert summary['latency_ms'] == {
        'max': 900.0,
        'p50': 10.0,
        'p95': 900.0,
        'p99': 900.0,
    }
    assert summary['errors'] == {'http_status': 1}
    assert summary['error_rate'] == 0.5
    assert summary['response_bytes'] == 15
    assert capacity.evaluate(
        summary,
        max_error_rate=0,
        max_p95_ms=750,
        min_rate_ratio=0.9,
    ) == [
        'error rate 50.00% exceeded 0.00%',
        'p95 900.000ms exceeded 750.000ms',
        'throughput 2.000/s was below 9.000/s',
    ]


def test_cli_refuses_public_production_target_without_sending(monkeypatch, capsys):
    called = False

    def forbidden_run(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(capacity, 'run', forbidden_run)

    assert capacity.main(['--origin', 'https://pcep.micutu.com:443']) == 2
    assert called is False
    assert 'refuses non-loopback' in capsys.readouterr().err
