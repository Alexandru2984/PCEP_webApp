import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


spec = importlib.util.spec_from_file_location(
    'database_security_check',
    Path(__file__).resolve().parents[3] / 'scripts/database_security_check.py',
)
security = importlib.util.module_from_spec(spec)
spec.loader.exec_module(security)


class FakeReleaseError(RuntimeError):
    pass


def deploy_module(verifier):
    class ReleaseConfig:
        def __init__(self, **values):
            self.__dict__.update(values)

    return SimpleNamespace(
        ReleaseConfig=ReleaseConfig,
        ReleaseError=FakeReleaseError,
        verify_database_roles=verifier,
    )


def test_verified_posture_writes_a_minimal_private_atomic_marker(tmp_path):
    status = tmp_path / 'state' / 'last-success.json'
    status.parent.mkdir(mode=0o700)
    calls = []

    def verify(config):
        calls.append(config)
        return {'app_schema_create': False}

    payload = security.execute(
        tmp_path,
        status,
        database_container='test_db',
        now=datetime(2026, 10, 14, 12, tzinfo=timezone.utc),
        deploy_module=deploy_module(verify),
    )

    assert len(calls) == 1
    assert calls[0].database_container == 'test_db'
    assert payload == {'completed_at': '2026-10-14T12:00:00Z', 'schema': 1}
    assert json.loads(status.read_text()) == payload
    assert status.stat().st_mode & 0o777 == 0o600
    assert list(status.parent.glob('.*.partial-*')) == []


def test_failed_posture_does_not_replace_the_last_success(tmp_path):
    status = tmp_path / 'state' / 'last-success.json'
    status.parent.mkdir(mode=0o700)
    previous = {'completed_at': '2026-10-14T10:00:00Z', 'schema': 1}
    status.write_text(json.dumps(previous) + '\n')
    status.chmod(0o600)

    def reject(_config):
        raise FakeReleaseError('least-privilege posture drifted')

    with pytest.raises(security.DatabaseSecurityError, match='posture drifted'):
        security.execute(
            tmp_path,
            status,
            deploy_module=deploy_module(reject),
        )

    assert json.loads(status.read_text()) == previous


def test_status_refuses_symlinks_and_public_directories(tmp_path):
    target = tmp_path / 'target'
    target.write_text('preserve')
    status = tmp_path / 'last-success.json'
    status.symlink_to(target)

    with pytest.raises(security.DatabaseSecurityError, match='real file'):
        security.write_success_status(status)
    assert target.read_text() == 'preserve'

    public = tmp_path / 'public'
    public.mkdir(mode=0o777)
    public.chmod(0o777)
    with pytest.raises(security.DatabaseSecurityError, match='not writable'):
        security.write_success_status(public / 'status.json')


@pytest.mark.parametrize('value', ['', '../db', 'db name', 'db;id', 'x' * 129])
def test_container_name_is_bounded(value):
    with pytest.raises(security.DatabaseSecurityError, match='container'):
        security.validate_container_name(value)
