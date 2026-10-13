import hashlib
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    'operations_health', PROJECT_ROOT / 'scripts/operations_health.py'
)
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)
backup_spec = importlib.util.spec_from_file_location(
    'database_backup_for_health', PROJECT_ROOT / 'scripts/database_backup.py'
)
backup = importlib.util.module_from_spec(backup_spec)
backup_spec.loader.exec_module(backup)


def complete_backup(root, stamp):
    path = root / f'pcep_db_daily_{stamp}.sql.gz'
    path.write_bytes(stamp.encode())
    path.chmod(0o600)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    checksum = path.with_name(f'{path.name}.sha256')
    checksum.write_text(f'{digest}  {path.name}\n')
    checksum.chmod(0o600)
    return path


def restore_status(path, completed_at):
    path.write_text(json.dumps({'schema': 1, 'completed_at': completed_at}) + '\n')
    path.chmod(0o600)


def test_healthy_recovery_attestation_is_minimal_atomic_and_publicly_readable(tmp_path):
    backups = tmp_path / 'backups'
    backups.mkdir(mode=0o700)
    complete_backup(backups, '20261013T080000Z')
    marker = tmp_path / 'restore.json'
    restore_status(marker, '2026-10-12T08:00:00Z')
    output = tmp_path / 'public' / 'status.json'
    output.parent.mkdir(mode=0o755)
    now = datetime(2026, 10, 13, 9, tzinfo=timezone.utc)

    payload = health.execute(backups, marker, output, now=now, backup_module=backup)

    assert payload == {
        'checked_at': '2026-10-13T09:00:00Z',
        'schema': 1,
        'status': 'ok',
    }
    assert json.loads(output.read_text()) == payload
    assert output.stat().st_mode & 0o777 == 0o644
    assert list(output.parent.glob('.*.partial-*')) == []


@pytest.mark.parametrize(
    'backup_stamp,restore_completed',
    [
        ('20261010T080000Z', '2026-10-12T08:00:00Z'),
        ('20261013T080000Z', '2026-10-01T08:00:00Z'),
    ],
)
def test_stale_recovery_component_publishes_only_a_generic_degraded_state(
    tmp_path, backup_stamp, restore_completed
):
    backups = tmp_path / 'backups'
    backups.mkdir(mode=0o700)
    complete_backup(backups, backup_stamp)
    marker = tmp_path / 'restore.json'
    restore_status(marker, restore_completed)
    output = tmp_path / 'public' / 'status.json'
    output.parent.mkdir(mode=0o755)

    with pytest.raises(health.OperationsHealthError, match='stale'):
        health.execute(
            backups,
            marker,
            output,
            now=datetime(2026, 10, 13, 9, tzinfo=timezone.utc),
            backup_module=backup,
        )

    assert json.loads(output.read_text()) == {
        'checked_at': '2026-10-13T09:00:00Z',
        'schema': 1,
        'status': 'degraded',
    }
    assert 'backup' not in output.read_text()
    assert 'restore' not in output.read_text()


def test_restore_marker_rejects_extra_fields_and_unsafe_permissions(tmp_path):
    marker = tmp_path / 'restore.json'
    marker.write_text(
        json.dumps(
            {
                'schema': 1,
                'completed_at': '2026-10-13T08:00:00Z',
                'backup': 'must-not-be-accepted',
            }
        )
    )
    marker.chmod(0o600)
    with pytest.raises(health.OperationsHealthError, match='shape'):
        health.read_restore_status(marker)

    restore_status(marker, '2026-10-13T08:00:00Z')
    marker.chmod(0o622)
    with pytest.raises(health.OperationsHealthError, match='permissions'):
        health.read_restore_status(marker)


def test_public_status_refuses_an_existing_symlink(tmp_path):
    target = tmp_path / 'target'
    target.write_text('preserve')
    output = tmp_path / 'status.json'
    output.symlink_to(target)

    with pytest.raises(health.OperationsHealthError, match='real file'):
        health.write_public_status(
            output,
            'ok',
            datetime(2026, 10, 13, 9, tzinfo=timezone.utc),
        )

    assert target.read_text() == 'preserve'
    assert os.path.islink(output)


@pytest.mark.parametrize('value', [0, 337, 'invalid'])
def test_freshness_windows_are_bounded(value):
    with pytest.raises(Exception, match='age'):
        health.bounded_hours(value)
