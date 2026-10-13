#!/usr/bin/env python3
"""Bounded, read-only capacity smoke for the local PCEP backend origin."""

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
import ipaddress
import json
import math
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


PATHS = (
    '/api/quiz-set/?count=4',
    '/api/live/',
    '/api/quiz-set/?count=4',
    '/api/health/',
    '/api/quiz-set/?count=4',
    '/api/stats/',
    '/api/quiz-set/?count=4',
    '/api/stats/',
)
MAX_DURATION_SECONDS = 60
MAX_RATE_PER_SECOND = 50
MAX_CONCURRENCY = 20
MAX_TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class CapacityError(RuntimeError):
    pass


class RefuseRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def local_opener():
    return build_opener(ProxyHandler({}), RefuseRedirects())


@dataclass(frozen=True)
class ProbeResult:
    path: str
    status: int | None
    latency_ms: float
    response_bytes: int
    error: str | None = None


def bounded_int(value, *, label, minimum, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise CapacityError(f'{label} must be an integer.') from error
    if not minimum <= parsed <= maximum:
        raise CapacityError(f'{label} must be between {minimum} and {maximum}.')
    return parsed


def bounded_float(value, *, label, minimum, maximum):
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise CapacityError(f'{label} must be a number.') from error
    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        raise CapacityError(f'{label} must be between {minimum} and {maximum}.')
    return parsed


def loopback_origin(value):
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise CapacityError('Origin has an invalid port.') from error
    if (
        parsed.scheme not in {'http', 'https'}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip('/')
        or port is None
        or port < 1
    ):
        raise CapacityError('Origin must be a loopback HTTP(S) origin with an explicit port.')
    hostname = parsed.hostname.rstrip('.').lower()
    if hostname != 'localhost':
        try:
            is_loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            is_loopback = False
        if not is_loopback:
            raise CapacityError('Capacity smoke refuses non-loopback origins.')
    return value.rstrip('/')


def safe_host_header(value):
    if not value or len(value) > 253:
        raise CapacityError('Host header is invalid.')
    labels = value.rstrip('.').split('.')
    if any(
        not label
        or len(label) > 63
        or label.startswith('-')
        or label.endswith('-')
        or not all(
            character.isascii() and (character.isalnum() or character == '-')
            for character in label
        )
        for label in labels
    ):
        raise CapacityError('Host header is invalid.')
    return value.rstrip('.').lower()


def fetch(origin, path, host_header, timeout):
    started = time.monotonic()
    request = Request(
        f'{origin}{path}',
        method='GET',
        headers={
            'Accept': 'application/json',
            'Accept-Encoding': 'identity',
            'Connection': 'close',
            'Host': host_header,
            'User-Agent': 'pcep-capacity-smoke/1',
            'X-Forwarded-Proto': 'https',
        },
    )
    status = None
    size = 0
    error_kind = None
    try:
        # Building a local opener per worker avoids shared mutable handler state.
        # The redirect handler turns every 3xx into HTTPError, so a loopback
        # origin cannot bounce this bounded probe to a remote target.
        with local_opener().open(
            request,
            timeout=timeout,
        ) as response:
            status = response.status
            body = response.read(MAX_RESPONSE_BYTES + 1)
            size = len(body)
            if size > MAX_RESPONSE_BYTES:
                error_kind = 'response_too_large'
            elif status != 200:
                error_kind = 'http_status'
    except HTTPError as error:
        status = error.code
        error_kind = 'http_status'
        error.close()
    except (URLError, TimeoutError, OSError):
        error_kind = 'transport'
    return ProbeResult(
        path=path,
        status=status,
        latency_ms=(time.monotonic() - started) * 1000,
        response_bytes=size,
        error=error_kind,
    )


def percentile(values, percentage):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil((percentage / 100) * len(ordered)) - 1)
    return ordered[index]


def summarize(results, *, requested_rate, duration, elapsed):
    latencies = [result.latency_ms for result in results]
    statuses = {}
    errors = {}
    endpoints = {}
    for result in results:
        status = str(result.status) if result.status is not None else 'none'
        statuses[status] = statuses.get(status, 0) + 1
        endpoint = endpoints.setdefault(
            result.path,
            {'errors': 0, 'requests': 0, 'status_200': 0},
        )
        endpoint['requests'] += 1
        if result.status == 200 and result.error is None:
            endpoint['status_200'] += 1
        if result.error is not None:
            endpoint['errors'] += 1
            errors[result.error] = errors.get(result.error, 0) + 1

    total = len(results)
    error_count = sum(errors.values())
    return {
        'duration_seconds': round(duration, 3),
        'elapsed_seconds': round(elapsed, 3),
        'endpoints': endpoints,
        'errors': errors,
        'latency_ms': {
            'max': round(max(latencies), 3) if latencies else None,
            'p50': round(percentile(latencies, 50), 3) if latencies else None,
            'p95': round(percentile(latencies, 95), 3) if latencies else None,
            'p99': round(percentile(latencies, 99), 3) if latencies else None,
        },
        'requested_rate_per_second': requested_rate,
        'requests': total,
        'response_bytes': sum(result.response_bytes for result in results),
        'status_counts': statuses,
        'throughput_per_second': round(total / elapsed, 3) if elapsed > 0 else 0,
        'error_rate': round(error_count / total, 6) if total else 1.0,
    }


def run(origin, host_header, *, duration, rate, concurrency, timeout):
    results = []
    active = set()
    interval = 1 / rate
    started = time.monotonic()
    deadline = started + duration
    next_due = started
    request_index = 0

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        while next_due < deadline:
            if len(active) >= concurrency:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                completed, active = wait(
                    active,
                    timeout=remaining,
                    return_when=FIRST_COMPLETED,
                )
                if not completed:
                    break
                results.extend(future.result() for future in completed)

            now = time.monotonic()
            if now >= deadline:
                break
            if now < next_due:
                time.sleep(next_due - now)
                now = time.monotonic()
            if now >= deadline:
                break
            # Never repay scheduler lag as a burst. Move the next slot forward.
            if now - next_due > interval:
                next_due = now
            path = PATHS[request_index % len(PATHS)]
            active.add(executor.submit(fetch, origin, path, host_header, timeout))
            request_index += 1
            next_due += interval

        if active:
            completed, _ = wait(active)
            results.extend(future.result() for future in completed)

    elapsed = time.monotonic() - started
    return summarize(
        results,
        requested_rate=rate,
        duration=duration,
        elapsed=elapsed,
    )


def evaluate(summary, *, max_error_rate, max_p95_ms, min_rate_ratio):
    failures = []
    if not summary['requests']:
        failures.append('no requests completed')
        return failures
    if summary['error_rate'] > max_error_rate:
        failures.append(
            f"error rate {summary['error_rate']:.2%} exceeded {max_error_rate:.2%}"
        )
    if summary['latency_ms']['p95'] > max_p95_ms:
        failures.append(
            f"p95 {summary['latency_ms']['p95']:.3f}ms exceeded {max_p95_ms:.3f}ms"
        )
    minimum_rate = summary['requested_rate_per_second'] * min_rate_ratio
    if summary['throughput_per_second'] < minimum_rate:
        failures.append(
            f"throughput {summary['throughput_per_second']:.3f}/s was below {minimum_rate:.3f}/s"
        )
    return failures


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default='http://127.0.0.1:8001')
    parser.add_argument('--host-header', default='pcep.micutu.com')
    parser.add_argument('--duration', default=20)
    parser.add_argument('--rate', default=15)
    parser.add_argument('--concurrency', default=6)
    parser.add_argument('--timeout', default=5)
    parser.add_argument('--max-error-rate', default=0)
    parser.add_argument('--max-p95-ms', default=750)
    parser.add_argument('--min-rate-ratio', default=0.9)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        origin = loopback_origin(args.origin)
        host_header = safe_host_header(args.host_header)
        duration = bounded_int(
            args.duration,
            label='duration',
            minimum=1,
            maximum=MAX_DURATION_SECONDS,
        )
        rate = bounded_int(
            args.rate,
            label='rate',
            minimum=1,
            maximum=MAX_RATE_PER_SECOND,
        )
        concurrency = bounded_int(
            args.concurrency,
            label='concurrency',
            minimum=1,
            maximum=MAX_CONCURRENCY,
        )
        timeout = bounded_int(
            args.timeout,
            label='timeout',
            minimum=1,
            maximum=MAX_TIMEOUT_SECONDS,
        )
        max_error_rate = bounded_float(
            args.max_error_rate,
            label='max error rate',
            minimum=0,
            maximum=1,
        )
        max_p95_ms = bounded_float(
            args.max_p95_ms,
            label='max p95',
            minimum=1,
            maximum=30_000,
        )
        min_rate_ratio = bounded_float(
            args.min_rate_ratio,
            label='minimum rate ratio',
            minimum=0.1,
            maximum=1,
        )
        summary = run(
            origin,
            host_header,
            duration=duration,
            rate=rate,
            concurrency=concurrency,
            timeout=timeout,
        )
        failures = evaluate(
            summary,
            max_error_rate=max_error_rate,
            max_p95_ms=max_p95_ms,
            min_rate_ratio=min_rate_ratio,
        )
        summary['result'] = 'fail' if failures else 'pass'
        summary['threshold_failures'] = failures
        print(json.dumps(summary, sort_keys=True))
        return 1 if failures else 0
    except CapacityError as error:
        print(f'capacity smoke refused: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
