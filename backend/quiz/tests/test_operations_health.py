import hashlib
import importlib.util
import json
import os
import tempfile
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


def release_snapshot(root, name, payload=b'reviewed release asset'):
    snapshot = root / name
    snapshot.mkdir(mode=0o755)
    asset = snapshot / 'assets' / 'index.js'
    asset.parent.mkdir(mode=0o755)
    asset.write_bytes(payload)
    asset.chmod(0o644)
    return snapshot


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


def test_failed_public_status_write_durably_removes_its_temporary(
    tmp_path, monkeypatch
):
    output = tmp_path / 'public/status.json'
    output.parent.mkdir(mode=0o755)
    flushed = []
    monkeypatch.setattr(
        health.json,
        'dump',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError('primary status write failure')
        ),
    )
    monkeypatch.setattr(
        health,
        'fsync_directory',
        lambda path: flushed.append(Path(path)),
    )

    with pytest.raises(OSError, match='primary status write failure'):
        health.write_public_status(
            output,
            'ok',
            datetime(2026, 10, 16, 2, tzinfo=timezone.utc),
        )

    assert list(output.parent.glob('.status.json.partial-*')) == []
    assert flushed == [output.parent]
    assert not output.exists()


def test_cleanup_failure_does_not_mask_the_public_status_error(
    tmp_path, monkeypatch, capsys
):
    output = tmp_path / 'public/status.json'
    output.parent.mkdir(mode=0o755)
    monkeypatch.setattr(
        health.json,
        'dump',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError('primary status write failure')
        ),
    )
    monkeypatch.setattr(
        health,
        'fsync_directory',
        lambda _path: (_ for _ in ()).throw(
            OSError('cleanup directory flush failure')
        ),
    )

    with pytest.raises(OSError, match='primary status write failure') as caught:
        health.write_public_status(
            output,
            'degraded',
            datetime(2026, 10, 16, 2, tzinfo=timezone.utc),
        )

    assert any(
        'cleanup directory flush failure' in note
        for note in getattr(caught.value, '__notes__', ())
    )
    assert 'Operations health cleanup warning' in capsys.readouterr().err
    assert list(output.parent.glob('.status.json.partial-*')) == []
    assert not output.exists()


@pytest.mark.parametrize(
    'name',
    [
        '.frontend.release-a1_b2c3d',
        '.static.release-12345678',
        '.seo.release-abcdefgh',
    ],
)
def test_fresh_release_staging_is_allowed(tmp_path, monkeypatch, name):
    root = tmp_path / 'releases'
    root.mkdir(mode=0o755)
    stage = root / name
    stage.mkdir(mode=0o700)
    (root / '.frontend.previous-20261015T010000Z-deadbeef').mkdir()
    (root / 'frontend.bak.20261015').mkdir()
    now = datetime(2026, 10, 16, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(
        health,
        'release_staging_changed_at',
        lambda _details: datetime(2026, 10, 16, 0, 30, tzinfo=timezone.utc),
    )

    assert health.verify_release_staging(root, 2, now) == [stage]


def test_tempfile_stage_name_matches_the_health_contract(tmp_path):
    generated = Path(tempfile.mkdtemp(prefix='.frontend.release-', dir=tmp_path))

    assert health.RELEASE_STAGE_PATTERN.fullmatch(generated.name)


def test_stale_release_staging_publishes_only_generic_degraded_state(
    tmp_path, monkeypatch
):
    backups = tmp_path / 'backups'
    backups.mkdir(mode=0o700)
    complete_backup(backups, '20261016T000000Z')
    restore = tmp_path / 'restore.json'
    restore_status(restore, '2026-10-15T23:00:00Z')
    output = tmp_path / 'public/status.json'
    output.parent.mkdir(mode=0o755)
    release_root = tmp_path / 'releases'
    release_root.mkdir(mode=0o755)
    stage = release_root / '.frontend.release-abcdefgh'
    stage.mkdir(mode=0o700)
    monkeypatch.setattr(
        health,
        'release_staging_changed_at',
        lambda _details: datetime(2026, 10, 15, 22, 59, tzinfo=timezone.utc),
    )

    with pytest.raises(
        health.OperationsHealthError,
        match=r'Stale release staging.*\.frontend\.release-abcdefgh',
    ):
        health.execute(
            backups,
            restore,
            output,
            now=datetime(2026, 10, 16, 1, tzinfo=timezone.utc),
            backup_module=backup,
            release_root=release_root,
            release_staging_max_age_hours=2,
        )

    assert json.loads(output.read_text())['status'] == 'degraded'
    assert stage.name not in output.read_text()


def test_release_staging_rejects_malformed_entries_symlinks_and_future_time(
    tmp_path, monkeypatch
):
    root = tmp_path / 'releases'
    root.mkdir(mode=0o755)
    malformed = root / '.frontend.release-not_an_expected_name'
    malformed.mkdir()
    now = datetime(2026, 10, 16, 1, tzinfo=timezone.utc)

    with pytest.raises(health.OperationsHealthError, match='Unsafe release staging'):
        health.verify_release_staging(root, 2, now)

    malformed.rmdir()
    unsafe = root / '.seo.release-abcdefgh'
    unsafe.symlink_to(root, target_is_directory=True)
    with pytest.raises(health.OperationsHealthError, match='Unsafe release staging'):
        health.verify_release_staging(root, 2, now)

    unsafe.unlink()
    stage = root / '.static.release-12345678'
    stage.mkdir(mode=0o700)
    monkeypatch.setattr(
        health,
        'release_staging_changed_at',
        lambda _details: datetime(2026, 10, 16, 1, 6, tzinfo=timezone.utc),
    )
    with pytest.raises(health.OperationsHealthError, match='unexpectedly in the future'):
        health.verify_release_staging(root, 2, now)


def test_release_snapshot_inventory_accepts_only_bounded_finalized_trees(tmp_path):
    release_root = tmp_path / 'releases'
    release_root.mkdir(mode=0o755)
    backup_root = tmp_path / 'deployment-backups'
    backup_root.mkdir(mode=0o700)
    for index in range(5):
        release_snapshot(
            release_root,
            f'.frontend.previous-2026101{index}T010203Z-{index:08x}',
        )
        release_snapshot(
            backup_root,
            f'frontend.2026101{index}T010203Z-{index:08x}',
        )
    (release_root / 'frontend.bak.20260620-010654').mkdir()
    (backup_root / 'pcep_db_pre_review.sql.gz').write_bytes(b'out of scope')

    inventory = health.verify_release_snapshot_inventory(
        release_root,
        backup_root,
    )

    assert inventory['rollback']['count'] == 5
    assert inventory['backup']['count'] == 5
    assert inventory['rollback']['allocated_bytes'] > 0
    assert inventory['backup']['allocated_bytes'] > 0


@pytest.mark.parametrize('location', ['rollback', 'backup'])
def test_release_snapshot_inventory_rejects_excess_count(tmp_path, location):
    release_root = tmp_path / 'releases'
    release_root.mkdir(mode=0o755)
    backup_root = tmp_path / 'deployment-backups'
    backup_root.mkdir(mode=0o700)
    root = release_root if location == 'rollback' else backup_root
    prefix = '.frontend.previous-' if location == 'rollback' else 'frontend.'
    for index in range(6):
        release_snapshot(
            root,
            f'{prefix}2026101{index}T010203Z-{index:08x}',
        )

    with pytest.raises(
        health.OperationsHealthError,
        match=rf'Frontend {location} snapshot count exceeds',
    ):
        health.verify_release_snapshot_inventory(
            release_root,
            backup_root,
            maximum=5,
        )


def test_release_snapshot_inventory_rejects_malformed_and_unsafe_entries(
    tmp_path,
):
    release_root = tmp_path / 'releases'
    release_root.mkdir(mode=0o755)
    backup_root = tmp_path / 'deployment-backups'
    backup_root.mkdir(mode=0o700)
    malformed = release_root / '.frontend.previous-not-a-reviewed-snapshot'
    malformed.mkdir()

    with pytest.raises(health.OperationsHealthError, match='Unsafe rollback'):
        health.verify_release_snapshot_inventory(release_root, backup_root)

    malformed.rmdir()
    unsafe = (
        release_root / '.frontend.previous-20261019T010203Z-deadbeef'
    )
    unsafe.symlink_to(release_root, target_is_directory=True)
    with pytest.raises(
        health.OperationsHealthError,
        match='Unsafe release snapshot entry',
    ):
        health.verify_release_snapshot_inventory(release_root, backup_root)

    unsafe.unlink()
    snapshot = release_snapshot(
        release_root,
        '.frontend.previous-20261019T010203Z-deadbeef',
    )
    asset = snapshot / 'assets/index.js'
    asset.chmod(0o666)
    with pytest.raises(
        health.OperationsHealthError,
        match='Unsafe release snapshot entry',
    ):
        health.verify_release_snapshot_inventory(release_root, backup_root)


def test_release_snapshot_inventory_rejects_excess_allocation(
    tmp_path, monkeypatch
):
    release_root = tmp_path / 'releases'
    release_root.mkdir(mode=0o755)
    backup_root = tmp_path / 'deployment-backups'
    backup_root.mkdir(mode=0o700)
    for index in range(2):
        release_snapshot(
            release_root,
            f'.frontend.previous-2026101{index}T010203Z-{index:08x}',
        )
    monkeypatch.setattr(
        health,
        'snapshot_allocated_bytes',
        lambda _path: 40 * 1024 * 1024,
    )

    with pytest.raises(
        health.OperationsHealthError,
        match='rollback snapshot allocation exceeds',
    ):
        health.verify_release_snapshot_inventory(
            release_root,
            backup_root,
            max_allocated_mib=64,
        )


def test_unsafe_release_snapshot_publishes_only_generic_degraded_state(tmp_path):
    backups = tmp_path / 'daily'
    backups.mkdir(mode=0o700)
    complete_backup(backups, '20261019T080000Z')
    restore = tmp_path / 'restore.json'
    restore_status(restore, '2026-10-19T08:00:00Z')
    output = tmp_path / 'public/status.json'
    output.parent.mkdir(mode=0o755)
    release_root = tmp_path / 'releases'
    release_root.mkdir(mode=0o755)
    deployment_root = tmp_path / 'deployment-backups'
    deployment_root.mkdir(mode=0o700)
    sensitive_name = '.frontend.previous-private-incident-evidence'
    (release_root / sensitive_name).mkdir()

    with pytest.raises(health.OperationsHealthError, match=sensitive_name):
        health.execute(
            backups,
            restore,
            output,
            now=datetime(2026, 10, 19, 9, tzinfo=timezone.utc),
            backup_module=backup,
            release_root=release_root,
            deployment_backup_root=deployment_root,
        )

    assert json.loads(output.read_text())['status'] == 'degraded'
    assert sensitive_name not in output.read_text()


@pytest.mark.parametrize('kind', ['partial', 'stderr'])
def test_fresh_deployment_backup_temporary_is_allowed(
    tmp_path, monkeypatch, kind
):
    root = tmp_path / 'deployment-backups'
    root.mkdir(mode=0o700)
    temporary = root / (
        f'.pcep_db_20261018T010203Z.sql.gz.{kind}-' + ('a' * 32)
    )
    temporary.write_bytes(b'private in-flight evidence')
    temporary.chmod(0o600)
    (root / 'pcep_db_20261017T010203Z.sql.gz').write_bytes(b'complete')
    now = datetime(2026, 10, 18, 2, tzinfo=timezone.utc)
    monkeypatch.setattr(
        health,
        'release_staging_changed_at',
        lambda _details: datetime(2026, 10, 18, 1, 30, tzinfo=timezone.utc),
    )

    assert health.verify_deployment_backup_temporaries(root, 2, now) == [
        temporary
    ]


def test_stale_deployment_backup_temporary_publishes_generic_degraded_state(
    tmp_path, monkeypatch
):
    backups = tmp_path / 'daily'
    backups.mkdir(mode=0o700)
    complete_backup(backups, '20261018T010000Z')
    restore = tmp_path / 'restore.json'
    restore_status(restore, '2026-10-18T01:00:00Z')
    output = tmp_path / 'public/status.json'
    output.parent.mkdir(mode=0o755)
    deployment = tmp_path / 'deployment-backups'
    deployment.mkdir(mode=0o700)
    temporary = deployment / (
        '.pcep_db_20261017T220000Z.sql.gz.partial-' + ('b' * 32)
    )
    temporary.write_bytes(b'private partial dump canary')
    temporary.chmod(0o600)
    monkeypatch.setattr(
        health,
        'release_staging_changed_at',
        lambda _details: datetime(2026, 10, 17, 22, tzinfo=timezone.utc),
    )

    with pytest.raises(
        health.OperationsHealthError,
        match=r'Stale deployment backup temporary.*\.partial-',
    ):
        health.execute(
            backups,
            restore,
            output,
            now=datetime(2026, 10, 18, 2, 1, tzinfo=timezone.utc),
            backup_module=backup,
            deployment_backup_root=deployment,
            deployment_backup_temporary_max_age_hours=2,
        )

    assert json.loads(output.read_text())['status'] == 'degraded'
    assert temporary.name not in output.read_text()
    assert 'private partial dump canary' not in output.read_text()


def test_deployment_backup_temporary_rejects_malformed_symlink_and_future_time(
    tmp_path, monkeypatch
):
    root = tmp_path / 'deployment-backups'
    root.mkdir(mode=0o700)
    malformed = root / '.pcep_db_bad.sql.gz.partial-not-a-uuid'
    malformed.write_bytes(b'unsafe')
    now = datetime(2026, 10, 18, 2, tzinfo=timezone.utc)

    with pytest.raises(health.OperationsHealthError, match='Unsafe deployment'):
        health.verify_deployment_backup_temporaries(root, 2, now)

    malformed.unlink()
    name = '.pcep_db_20261018T010203Z.sql.gz.stderr-' + ('c' * 32)
    public = root / name
    public.write_bytes(b'unsafe permissions')
    public.chmod(0o640)
    with pytest.raises(health.OperationsHealthError, match='Unsafe deployment'):
        health.verify_deployment_backup_temporaries(root, 2, now)

    public.unlink()
    unsafe = root / name
    unsafe.symlink_to(root / 'target')
    with pytest.raises(health.OperationsHealthError, match='Unsafe deployment'):
        health.verify_deployment_backup_temporaries(root, 2, now)

    unsafe.unlink()
    future = root / name
    future.write_bytes(b'private stderr')
    future.chmod(0o600)
    monkeypatch.setattr(
        health,
        'release_staging_changed_at',
        lambda _details: datetime(2026, 10, 18, 2, 6, tzinfo=timezone.utc),
    )
    with pytest.raises(health.OperationsHealthError, match='unexpectedly in the future'):
        health.verify_deployment_backup_temporaries(root, 2, now)


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


@pytest.mark.parametrize('value', [4, 101, 'invalid'])
def test_release_snapshot_count_is_bounded(value):
    with pytest.raises(Exception, match='snapshot maximum'):
        health.bounded_snapshot_count(value)


@pytest.mark.parametrize('value', [63, 10241, 'invalid'])
def test_release_snapshot_allocation_is_bounded(value):
    with pytest.raises(Exception, match='snapshot allocation'):
        health.bounded_snapshot_mebibytes(value)


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
    assert '--release-root /var/www/pcep' in service
    assert '--release-staging-max-age-hours 2' in service
    assert '--deployment-backup-root /home/micu/backups/pcep' in service
    assert '--deployment-backup-temporary-max-age-hours 2' in service
    assert '--release-snapshot-maximum 10' in service
    assert '--release-snapshot-max-allocated-mib 512' in service
    assert '--verify-installation' in service
    assert '--verify-nginx-installation' in service
    assert '--verify-container-runtime' in service
    assert 'ReadOnlyPaths=/var/lib/pcep-db-security' in service
    assert 'ReadOnlyPaths=/var/www/pcep' in service
    assert 'ReadOnlyPaths=/home/micu/backups/pcep' in service
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
