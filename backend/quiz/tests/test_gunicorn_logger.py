from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from gunicorn.glogging import Logger

from pcep_project.gunicorn_logger import ProductionLogger


def environ(**overrides):
    values = {
        'REQUEST_METHOD': 'GET',
        'PATH_INFO': '/api/health/',
        'HTTP_X_PCEP_INTERNAL_HEALTHCHECK': '1',
        'REMOTE_ADDR': '127.0.0.1',
    }
    values.update(overrides)
    return values


def test_successful_internal_healthcheck_is_not_logged(monkeypatch):
    parent_access = Mock()
    monkeypatch.setattr(Logger, 'access', parent_access)
    logger = object.__new__(ProductionLogger)

    logger.access(SimpleNamespace(status='200 OK'), None, environ(), timedelta())

    parent_access.assert_not_called()


def test_failed_internal_healthcheck_remains_visible(monkeypatch):
    parent_access = Mock()
    monkeypatch.setattr(Logger, 'access', parent_access)
    logger = object.__new__(ProductionLogger)
    response = SimpleNamespace(status=503)
    request_time = timedelta(milliseconds=20)
    request_environ = environ()

    logger.access(response, None, request_environ, request_time)

    parent_access.assert_called_once_with(response, None, request_environ, request_time)


def test_external_header_cannot_suppress_access_logging(monkeypatch):
    parent_access = Mock()
    monkeypatch.setattr(Logger, 'access', parent_access)
    logger = object.__new__(ProductionLogger)
    response = SimpleNamespace(status=200)
    request_time = timedelta(milliseconds=5)
    request_environ = environ(REMOTE_ADDR='172.18.0.1')

    logger.access(response, None, request_environ, request_time)

    parent_access.assert_called_once_with(response, None, request_environ, request_time)
