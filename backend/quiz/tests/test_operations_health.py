import hashlib
import importlib.util
import json
import os
from datetime import date, datetime, timezone
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


def offsite_status(path, completed_at):
    path.write_text(
        f'timestamp={completed_at}\n'
        'backup=pcep_db_daily_20261027T080000Z.sql.gz\n'
        'remote=pcep-drive-crypt\n'
        f'sha256={"a" * 64}\n'
    )
    path.chmod(0o600)


def database_security_status(path, completed_at):
    path.write_text(
        json.dumps({'schema': 1, 'completed_at': completed_at}) + '\n'
    )
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
    assert output.stat().st_mode & 0o777 == 0o600
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


def test_offsite_deadline_fails_closed_until_a_fresh_success_exists(tmp_path):
    backups = tmp_path / 'backups'
    backups.mkdir(mode=0o700)
    complete_backup(backups, '20261026T080000Z')
    marker = tmp_path / 'restore.json'
    restore_status(marker, '2026-10-26T08:00:00Z')
    output = tmp_path / 'public' / 'status.json'
    output.parent.mkdir(mode=0o755)
    offsite = tmp_path / 'offsite-success'
    deadline = date(2026, 10, 27)

    before = health.execute(
        backups,
        marker,
        output,
        now=datetime(2026, 10, 26, 9, tzinfo=timezone.utc),
        backup_module=backup,
        offsite_status=offsite,
        offsite_required_after=deadline,
    )
    assert before['status'] == 'ok'

    with pytest.raises(health.OperationsHealthError, match='Offsite backup'):
        health.execute(
            backups,
            marker,
            output,
            now=datetime(2026, 10, 27, 9, tzinfo=timezone.utc),
            backup_module=backup,
            offsite_status=offsite,
            offsite_required_after=deadline,
        )
    assert json.loads(output.read_text())['status'] == 'degraded'

    offsite_status(offsite, '2026-10-27T08:00:00Z')
    healthy = health.execute(
        backups,
        marker,
        output,
        now=datetime(2026, 10, 27, 9, tzinfo=timezone.utc),
        backup_module=backup,
        offsite_status=offsite,
        offsite_required_after=deadline,
    )
    assert healthy['status'] == 'ok'

    offsite_status(offsite, '2026-10-26T08:59:59Z')
    with pytest.raises(health.OperationsHealthError, match='offsite backup.*stale'):
        health.execute(
            backups,
            marker,
            output,
            now=datetime(2026, 10, 27, 9, tzinfo=timezone.utc),
            backup_module=backup,
            offsite_status=offsite,
            offsite_required_after=deadline,
        )


def test_offsite_marker_rejects_extra_fields_and_public_permissions(tmp_path):
    marker = tmp_path / 'offsite-success'
    offsite_status(marker, '2026-10-27T08:00:00Z')
    marker.write_text(marker.read_text() + 'extra=must-not-be-accepted\n')

    with pytest.raises(health.OperationsHealthError, match='shape'):
        health.read_offsite_status(marker)

    offsite_status(marker, '2026-10-27T08:00:00Z')
    marker.chmod(0o644)
    with pytest.raises(health.OperationsHealthError, match='permissions'):
        health.read_offsite_status(marker)


def test_database_security_marker_is_required_and_fresh(tmp_path):
    backups = tmp_path / 'backups'
    backups.mkdir(mode=0o700)
    complete_backup(backups, '20261014T110000Z')
    restore = tmp_path / 'restore.json'
    restore_status(restore, '2026-10-14T10:00:00Z')
    security_marker = tmp_path / 'database-security.json'
    output = tmp_path / 'public' / 'status.json'
    output.parent.mkdir(mode=0o755)
    now = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)

    with pytest.raises(health.OperationsHealthError, match='security.*unavailable'):
        health.execute(
            backups,
            restore,
            output,
            now=now,
            backup_module=backup,
            database_security_status=security_marker,
        )
    assert json.loads(output.read_text())['status'] == 'degraded'

    database_security_status(security_marker, '2026-10-14T10:00:00Z')
    security_marker.chmod(0o644)
    with pytest.raises(health.OperationsHealthError, match='permissions'):
        health.verify_database_security_freshness(security_marker, 2, now)
    security_marker.chmod(0o600)
    assert health.execute(
        backups,
        restore,
        output,
        now=now,
        backup_module=backup,
        database_security_status=security_marker,
    )['status'] == 'ok'

    database_security_status(security_marker, '2026-10-14T09:59:59Z')
    with pytest.raises(health.OperationsHealthError, match='security check.*stale'):
        health.execute(
            backups,
            restore,
            output,
            now=now,
            backup_module=backup,
            database_security_status=security_marker,
        )


def test_installation_drift_publishes_only_generic_degraded_state(tmp_path):
    backups = tmp_path / 'backups'
    backups.mkdir(mode=0o700)
    complete_backup(backups, '20261014T110000Z')
    restore = tmp_path / 'restore.json'
    restore_status(restore, '2026-10-14T10:00:00Z')
    output = tmp_path / 'public/status.json'
    output.parent.mkdir(mode=0o755)

    class DriftingInstallation:
        @staticmethod
        def verify_installation():
            raise RuntimeError('SENSITIVE_INSTALLATION_DETAIL')

    with pytest.raises(
        health.OperationsHealthError,
        match='installation drift.*SENSITIVE_INSTALLATION_DETAIL',
    ):
        health.execute(
            backups,
            restore,
            output,
            now=datetime(2026, 10, 14, 12, tzinfo=timezone.utc),
            backup_module=backup,
            verify_installation=True,
            installation_module=DriftingInstallation,
        )

    assert json.loads(output.read_text())['status'] == 'degraded'
    assert 'SENSITIVE_INSTALLATION_DETAIL' not in output.read_text()


def test_container_drift_publishes_only_generic_degraded_state(tmp_path):
    backups = tmp_path / 'backups'
    backups.mkdir(mode=0o700)
    complete_backup(backups, '20261014T110000Z')
    restore = tmp_path / 'restore.json'
    restore_status(restore, '2026-10-14T10:00:00Z')
    output = tmp_path / 'public/status.json'
    output.parent.mkdir(mode=0o755)

    class DriftingRuntime:
        @staticmethod
        def verify_container_runtime():
            raise RuntimeError('SENSITIVE_CONTAINER_DETAIL')

    with pytest.raises(
        health.OperationsHealthError,
        match='runtime drift.*SENSITIVE_CONTAINER_DETAIL',
    ):
        health.execute(
            backups,
            restore,
            output,
            now=datetime(2026, 10, 14, 12, tzinfo=timezone.utc),
            backup_module=backup,
            verify_container_runtime=True,
            container_runtime_module=DriftingRuntime,
        )

    assert json.loads(output.read_text())['status'] == 'degraded'
    assert 'SENSITIVE_CONTAINER_DETAIL' not in output.read_text()


def test_nginx_drift_publishes_only_generic_degraded_state(tmp_path):
    backups = tmp_path / 'backups'
    backups.mkdir(mode=0o700)
    complete_backup(backups, '20261014T110000Z')
    restore = tmp_path / 'restore.json'
    restore_status(restore, '2026-10-14T10:00:00Z')
    output = tmp_path / 'public/status.json'
    output.parent.mkdir(mode=0o755)

    class DriftingNginx:
        @staticmethod
        def verify_installation():
            raise RuntimeError('SENSITIVE_NGINX_DETAIL')

    with pytest.raises(
        health.OperationsHealthError,
        match='Nginx installation drift.*SENSITIVE_NGINX_DETAIL',
    ):
        health.execute(
            backups,
            restore,
            output,
            now=datetime(2026, 10, 14, 12, tzinfo=timezone.utc),
            backup_module=backup,
            verify_nginx_installation=True,
            nginx_installation_module=DriftingNginx,
        )

    assert json.loads(output.read_text())['status'] == 'degraded'
    assert 'SENSITIVE_NGINX_DETAIL' not in output.read_text()


def test_private_diagnostic_is_single_line_and_bounded():
    diagnostic = health.private_diagnostic(
        'Verifier failed',
        RuntimeError('first\nsecond\x00' + ('x' * 600)),
    )

    assert diagnostic.startswith('Verifier failed: first second ')
    assert '\n' not in diagnostic
    assert '\x00' not in diagnostic
    assert len(diagnostic.removeprefix('Verifier failed: ')) == 512
    assert diagnostic.endswith('...')


@pytest.mark.parametrize('value', [0, 337, 'invalid'])
def test_freshness_windows_are_bounded(value):
    with pytest.raises(Exception, match='age'):
        health.bounded_hours(value)


def test_systemd_grants_only_nginx_an_explicit_read_acl():
    service = (
        PROJECT_ROOT / 'ops/systemd/pcep-operations-health.service'
    ).read_text()

    assert 'UMask=0077' in service
    assert 'StateDirectoryMode=0750' in service
    assert 'Group=www-data' in service
    assert (
        'ExecStartPost=/usr/bin/setfacl --modify user:www-data:r-- '
        '/var/lib/pcep-operations-health/status.json'
    ) in service
    assert (
        'ExecStopPost=-/usr/bin/setfacl --modify user:www-data:r-- '
        '/var/lib/pcep-operations-health/status.json'
    ) in service
    assert '--offsite-status /var/lib/pcep-db-offsite/last-success' in service
    assert '--offsite-required-after 2026-10-27' in service
    assert '--offsite-max-age-hours 24' in service
    assert 'ReadOnlyPaths=-/var/lib/pcep-db-offsite' in service
    assert (
        '--database-security-status /var/lib/pcep-db-security/last-success.json'
        in service
    )
    assert '--database-security-max-age-hours 2' in service
    assert '--verify-installation' in service
    assert '--verify-nginx-installation' in service
    assert '--verify-container-runtime' in service
    assert 'ReadOnlyPaths=/var/lib/pcep-db-security' in service
    assert 'IPAddressDeny=any' in service
    assert 'SystemCallFilter=@system-service' in service
    assert 'SystemCallErrorNumber=EPERM' in service


def test_database_security_timer_is_hourly_networkless_and_marker_only():
    service = (
        PROJECT_ROOT / 'ops/systemd/pcep-database-security.service'
    ).read_text()
    timer = (
        PROJECT_ROOT / 'ops/systemd/pcep-database-security.timer'
    ).read_text()

    assert 'StateDirectory=pcep-db-security' in service
    assert 'StateDirectoryMode=0700' in service
    assert 'PrivateNetwork=true' in service
    assert 'RestrictAddressFamilies=AF_UNIX' in service
    assert 'CapabilityBoundingSet=' in service
    assert 'NoNewPrivileges=true' in service
    assert '--status-file /var/lib/pcep-db-security/last-success.json' in service
    assert 'OnCalendar=*-*-* *:07:00' in timer
    assert 'Persistent=true' in timer
