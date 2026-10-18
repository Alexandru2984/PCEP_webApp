import gzip
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'deployment_backup_retention',
    Path(__file__).resolve().parents[3]
    / 'scripts/deployment_backup_retention.py',
)
retention = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retention)


def completed_backup(root, day, *, prefix='pcep_db'):
    path = root / f'{prefix}_202610{day:02d}T010000Z.sql.gz'
    with gzip.open(path, 'wb') as output:
        output.write(b'--\n-- PostgreSQL database dump\n--\nSELECT 1;\n')
    path.chmod(0o600)
    return path


def test_plan_keeps_newest_exact_backups_and_ignores_other_artifacts(tmp_path):
    root = tmp_path / 'backups'
    root.mkdir(mode=0o700)
    backups = [completed_backup(root, day) for day in range(1, 13)]
    legacy = root / 'pcep_db_20260924-184310.sql.gz'
    legacy.write_bytes(b'legacy')
    named = completed_backup(root, 1, prefix='pcep_db_pre_foundations')

    plan = retention.retention_plan(root, keep=10)

    assert [item.path for item in plan['keep']] == list(reversed(backups[2:]))
    assert [item.path for item in plan['remove']] == backups[:2]
    assert legacy.exists() and named.exists()


def test_apply_removes_oldest_first_and_flushes_each_unlink(
    tmp_path, monkeypatch
):
    root = tmp_path / 'backups'
    root.mkdir(mode=0o700)
    backups = [completed_backup(root, day) for day in range(1, 5)]
    plan = retention.retention_plan(root, keep=2)
    events = []
    original_unlink = Path.unlink

    def unlink(path, *args, **kwargs):
        events.append(('unlink', path.name))
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'unlink', unlink)
    monkeypatch.setattr(
        retention,
        'fsync_directory',
        lambda path: events.append(('fsync', Path(path).name)),
    )

    assert retention.apply_plan(plan) == backups[:2]
    assert events == [
        ('unlink', backups[0].name),
        ('fsync', 'backups'),
        ('unlink', backups[1].name),
        ('fsync', 'backups'),
    ]
    assert all(path.exists() for path in backups[2:])


@pytest.mark.parametrize(
    'unsafe_kind',
    ['corrupt', 'public', 'symlink', 'hardlink', 'future'],
)
def test_unsafe_exact_match_aborts_without_deleting_anything(
    tmp_path, unsafe_kind
):
    root = tmp_path / 'backups'
    root.mkdir(mode=0o700)
    backups = [completed_backup(root, day) for day in range(1, 5)]
    unsafe = backups[0]
    if unsafe_kind == 'corrupt':
        unsafe.write_bytes(b'not a gzip stream')
        unsafe.chmod(0o600)
    elif unsafe_kind == 'public':
        unsafe.chmod(0o644)
    else:
        if unsafe_kind == 'symlink':
            unsafe.unlink()
            unsafe.symlink_to(backups[1])
        elif unsafe_kind == 'hardlink':
            (root / 'unrelated-hardlink').hardlink_to(unsafe)
        else:
            unsafe = root / 'pcep_db_99991001T010000Z.sql.gz'
            unsafe.write_bytes(backups[1].read_bytes())
            unsafe.chmod(0o600)

    with pytest.raises(retention.DeploymentBackupRetentionError):
        retention.apply_retention(root, keep=2)

    assert all(path.exists() or path.is_symlink() for path in backups)


def test_apply_rechecks_content_and_identity_after_review(tmp_path):
    root = tmp_path / 'backups'
    root.mkdir(mode=0o700)
    backups = [completed_backup(root, day) for day in range(1, 4)]
    plan = retention.retention_plan(root, keep=2)
    target = backups[0]
    target.unlink()
    completed_backup(root, 1)

    with pytest.raises(
        retention.DeploymentBackupRetentionError,
        match='changed after review',
    ):
        retention.apply_plan(plan)

    assert target.exists()


def test_retention_refuses_a_concurrent_backend_deployment(tmp_path):
    root = tmp_path / 'backups'
    root.mkdir(mode=0o700)
    completed_backup(root, 1)
    lock_root = tmp_path / 'locks'

    with retention.exclusive_operation_lock(
        'backend-maintenance',
        root=lock_root,
    ):
        with pytest.raises(
            retention.DeploymentBackupRetentionError,
            match='already running',
        ):
            retention.execute(root, keep=2, lock_root=lock_root)
