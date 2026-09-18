from unittest.mock import MagicMock

import pytest
import wait_for_db


def test_probe_closes_the_connection(monkeypatch):
    connect = MagicMock()
    monkeypatch.setattr(wait_for_db.socket, 'create_connection', connect)
    wait_for_db.wait_for_database('db', 5432, 60)
    connect.assert_called_once()
    connect.return_value.__exit__.assert_called_once()


def test_probe_deadline_is_bounded(monkeypatch):
    now = [0]
    monkeypatch.setattr(wait_for_db.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(wait_for_db.time, 'sleep', lambda seconds: now.__setitem__(0, now[0] + seconds))
    connect = MagicMock(side_effect=OSError('unavailable'))
    monkeypatch.setattr(wait_for_db.socket, 'create_connection', connect)
    with pytest.raises(SystemExit, match='startup timed out'):
        wait_for_db.wait_for_database('db', 5432, 3)
    assert now[0] == 3
    assert connect.call_count == 3


@pytest.mark.parametrize('key,value', [('POSTGRES_PORT', 'invalid'), ('POSTGRES_PORT', '65536'), ('DB_STARTUP_TIMEOUT_SECONDS', '0'), ('DB_STARTUP_TIMEOUT_SECONDS', '301')])
def test_invalid_startup_settings_fail_cleanly(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(SystemExit, match='Invalid database startup'):
        wait_for_db.main()


def test_host_is_passed_as_data(monkeypatch):
    host = "localhost'); raise RuntimeError('injected') #"
    monkeypatch.setenv('POSTGRES_HOST', host)
    probe = MagicMock()
    monkeypatch.setattr(wait_for_db, 'wait_for_database', probe)
    wait_for_db.main()
    probe.assert_called_once_with(host, 5432, 60)
