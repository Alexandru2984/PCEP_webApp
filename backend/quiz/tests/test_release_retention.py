import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'release_retention',
    Path(__file__).resolve().parents[3] / 'scripts/release_retention.py',
)
retention = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retention)


def snapshot_roots(tmp_path, count=7):
    live_parent = tmp_path / 'live'
    target = live_parent / 'frontend'
    backup_root = tmp_path / 'backups'
    target.mkdir(parents=True)
    backup_root.mkdir()
    suffixes = [f'202609{i:02d}T120000Z-{i:08x}' for i in range(1, count + 1)]
    for suffix in suffixes:
        previous = live_parent / f'.frontend.previous-{suffix}'
        backup = backup_root / f'frontend.{suffix}'
        previous.mkdir()
        backup.mkdir()
        (previous / 'asset.js').write_text(suffix)
        (backup / 'asset.js').write_text(suffix)
    return target, backup_root, suffixes


def test_retention_plan_keeps_newest_complete_snapshots(tmp_path):
    target, backup_root, suffixes = snapshot_roots(tmp_path)
    plan = retention.retention_plan(target, backup_root, keep=5)

    assert [path.name for path in plan['previous']['keep']] == [
        f'.frontend.previous-{suffix}' for suffix in reversed(suffixes[-5:])
    ]
    assert [path.name for path in plan['backup']['remove']] == [
        f'frontend.{suffix}' for suffix in reversed(suffixes[:2])
    ]


def test_dry_run_reports_without_removing_anything(tmp_path, capsys):
    target, backup_root, _ = snapshot_roots(tmp_path)
    before = sorted(path.name for path in target.parent.iterdir())

    retention.execute(target, backup_root, keep=5)

    assert sorted(path.name for path in target.parent.iterdir()) == before
    assert 'Nothing removed' in capsys.readouterr().out


def test_apply_only_removes_matching_old_frontend_snapshots(tmp_path):
    target, backup_root, suffixes = snapshot_roots(tmp_path)
    security = backup_root / 'security-20260918'
    database = backup_root / 'pcep_db_20260925.sql.gz'
    static = backup_root / f'static.{suffixes[0]}'
    security.mkdir()
    database.write_text('database backup')
    static.mkdir()

    retention.execute(target, backup_root, keep=5, apply=True)

    assert len(list(target.parent.glob('.frontend.previous-*'))) == 5
    assert len(list(backup_root.glob('frontend.*'))) == 5
    assert security.is_dir()
    assert database.read_text() == 'database backup'
    assert static.is_dir()


def test_refuses_matching_symlinks_and_unsafe_target_names(tmp_path):
    target, backup_root, _ = snapshot_roots(tmp_path, count=2)
    unsafe = target.parent / '.frontend.previous-20260930T120000Z-deadbeef'
    unsafe.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match='Unsafe matching'):
        retention.retention_plan(target, backup_root)

    other = target.parent / 'uploads'
    other.mkdir()
    with pytest.raises(ValueError, match='frontend or static'):
        retention.retention_plan(other, backup_root)


@pytest.mark.parametrize('value', [0, 1, 101, 'nope'])
def test_requires_a_bounded_rollback_floor(value):
    with pytest.raises(Exception, match='keep'):
        retention.keep_count(value)
