import importlib.util
import hashlib
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'release_retention',
    Path(__file__).resolve().parents[3] / 'scripts/release_retention.py',
)
retention = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retention)


@pytest.fixture(autouse=True)
def use_fixture_runtime_hashes(monkeypatch, tmp_path):
    publisher = retention.load_publish_release()
    hashes = {
        name: hashlib.sha256(b'\x00asm' if name.endswith('.wasm') else b'complete').hexdigest()
        for name in publisher.PYODIDE_FILE_NAMES
    }
    monkeypatch.setattr(publisher, 'PYODIDE_SHA256', hashes)
    monkeypatch.setattr(publisher, 'DEFAULT_LOCK_ROOT', tmp_path / 'locks')
    monkeypatch.setattr(retention, 'load_publish_release', lambda: publisher)


def complete_frontend_release(root):
    files = [
        'index.html', 'sw.js', 'runner.html', 'runner-bridge.js', 'py-worker.js',
        'manifest.webmanifest', '.well-known/security.txt',
        'pyodide/VERSION', 'pyodide/pyodide.js',
        'pyodide/pyodide.asm.js', 'pyodide/pyodide.asm.wasm',
        'pyodide/pyodide-lock.json', 'pyodide/python_stdlib.zip',
    ]
    for name in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        content = b'\x00asm' if name.endswith('.wasm') else b'complete'
        if name == 'index.html':
            content = b'<!doctype html><html></html>'
        path.write_bytes(content)


def snapshot_roots(tmp_path, count=7):
    live_parent = tmp_path / 'live'
    target = live_parent / 'frontend'
    backup_root = tmp_path / 'backups'
    target.mkdir(parents=True)
    backup_root.mkdir()
    complete_frontend_release(target)
    suffixes = [f'202609{i:02d}T120000Z-{i:08x}' for i in range(1, count + 1)]
    for suffix in suffixes:
        previous = live_parent / f'.frontend.previous-{suffix}'
        backup = backup_root / f'frontend.{suffix}'
        previous.mkdir()
        backup.mkdir()
        complete_frontend_release(previous)
        complete_frontend_release(backup)
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


def test_retention_refuses_a_concurrent_publish(tmp_path):
    target, backup_root, _ = snapshot_roots(tmp_path)
    publisher = retention.load_publish_release()

    with publisher.exclusive_operation_lock(
        publisher.release_lock_name(target),
        root=publisher.DEFAULT_LOCK_ROOT,
    ):
        with pytest.raises(ValueError, match='already running'):
            retention.execute(target, backup_root, keep=5)

    assert len(list(target.parent.glob('.frontend.previous-*'))) == 7


def test_apply_only_removes_matching_old_frontend_snapshots(tmp_path, monkeypatch):
    target, backup_root, suffixes = snapshot_roots(tmp_path)
    security = backup_root / 'security-20260918'
    database = backup_root / 'pcep_db_20260925.sql.gz'
    static = backup_root / f'static.{suffixes[0]}'
    security.mkdir()
    database.write_text('database backup')
    static.mkdir()
    flushed = []
    monkeypatch.setattr(
        retention,
        'fsync_directory',
        lambda path: flushed.append(Path(path)),
    )

    retention.execute(target, backup_root, keep=5, apply=True)

    assert len(list(target.parent.glob('.frontend.previous-*'))) == 5
    assert len(list(backup_root.glob('frontend.*'))) == 5
    assert security.is_dir()
    assert database.read_text() == 'database backup'
    assert static.is_dir()
    assert flushed == [target.parent] * 2 + [backup_root] * 2


def test_directory_fsync_failure_stops_before_the_next_removal(
    tmp_path, monkeypatch
):
    target, backup_root, _suffixes = snapshot_roots(tmp_path, count=4)

    def fail_fsync(_path):
        raise OSError('simulated directory fsync failure')

    monkeypatch.setattr(retention, 'fsync_directory', fail_fsync)

    with pytest.raises(OSError, match='directory fsync failure'):
        retention.execute(target, backup_root, keep=2, apply=True)

    assert target.is_dir()
    assert len(list(target.parent.glob('.frontend.previous-*'))) == 3
    assert len(list(backup_root.glob('frontend.*'))) == 4


def test_invalid_new_snapshots_are_not_counted_as_retained_rollbacks(tmp_path):
    target, backup_root, suffixes = snapshot_roots(tmp_path, count=4)
    newest_previous = target.parent / f'.frontend.previous-{suffixes[-1]}'
    newest_backup = backup_root / f'frontend.{suffixes[-1]}'
    (newest_previous / 'runner.html').unlink()
    (newest_backup / 'runner.html').unlink()

    plan = retention.retention_plan(target, backup_root, keep=2)

    assert newest_previous in plan['previous']['remove']
    assert newest_previous in plan['previous']['invalid']
    assert newest_backup in plan['backup']['remove']
    assert newest_backup in plan['backup']['invalid']
    assert [path.name for path in plan['previous']['keep']] == [
        f'.frontend.previous-{suffixes[-2]}',
        f'.frontend.previous-{suffixes[-3]}',
    ]


def test_refuses_pruning_without_two_current_contract_rollbacks(tmp_path):
    target, backup_root, suffixes = snapshot_roots(tmp_path, count=2)
    invalid = target.parent / f'.frontend.previous-{suffixes[-1]}' / 'runner.html'
    invalid.unlink()

    with pytest.raises(ValueError, match='only 1 snapshot.*current frontend'):
        retention.retention_plan(target, backup_root, keep=2)

    assert len(list(target.parent.glob('.frontend.previous-*'))) == 2
    assert len(list(backup_root.glob('frontend.*'))) == 2


def test_refuses_pruning_when_the_live_release_is_invalid(tmp_path):
    target, backup_root, _suffixes = snapshot_roots(tmp_path)
    (target / 'runner.html').unlink()

    with pytest.raises(ValueError, match='Live frontend release is invalid'):
        retention.retention_plan(target, backup_root)


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
