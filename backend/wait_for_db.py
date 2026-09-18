"""Bounded startup probe; environment values are data, never Python source."""
import os
import socket
import time


def wait_for_database(host, port, timeout):
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            with socket.create_connection((host, port), timeout=min(2, remaining)):
                return
        except OSError:
            time.sleep(min(1, max(0, deadline - time.monotonic())))
    raise SystemExit('PostgreSQL startup timed out; check database readiness.')


def main():
    try:
        port = int(os.environ.get('POSTGRES_PORT', '5432'))
        timeout = int(os.environ.get('DB_STARTUP_TIMEOUT_SECONDS', '60'))
        if not 1 <= port <= 65535 or not 1 <= timeout <= 300:
            raise ValueError
    except ValueError:
        raise SystemExit('Invalid database startup port or timeout.') from None
    host = os.environ.get('POSTGRES_HOST', 'db')
    if not host:
        raise SystemExit('Database startup host is empty.')
    print('Waiting for PostgreSQL readiness...', flush=True)
    wait_for_database(host, port, timeout)
    print('PostgreSQL port is ready.', flush=True)


if __name__ == '__main__':
    main()
