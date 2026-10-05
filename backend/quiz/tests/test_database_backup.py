import gzip
import hashlib
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'database_backup',
    Path(__file__).resolve().parents[3] / 'scripts/database_backup.py',
)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def fake_dump(project_root, backup_root, container, stamp):
    assert project_root.is_dir()
    assert container == 'test_db'
    path = backup_root / f'pcep_db_daily_{stamp}.sql.gz'
    with gzip.open(path, 'wb') as output:
        output.write(b'-- PostgreSQL database dump\nSELECT 1;\n')
    path.chmod(0o600)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def completed_backup(root, day):
    path = root / f'pcep_db_daily_202610{day:02d}T010000Z.sql.gz'
    path.write_bytes(str(day).encode())
    path.chmod(0o600)
    checksum = backup.checksum_path(path)
    checksum.write_text(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n')
    checksum.chmod(0o600)
    return path


def test_daily_backup_is_private_checksummed_and_bounded(tmp_path):
    root = tmp_path / 'backups'
    root.mkdir()
    old = [completed_backup(root, day) for day in range(1, 9)]

    path, digest, removed = backup.execute(
        tmp_path,
        root,
        container='test_db',
        keep=7,
        now=datetime(2026, 10, 9, 1, tzinfo=timezone.utc),
        dump_creator=fake_dump,
    )

    assert path.stat().st_mode & 0o777 == 0o600
    checksum = backup.checksum_path(path)
    assert checksum.stat().st_mode & 0o777 == 0o600
    assert checksum.read_text() == f'{digest}  {path.name}\n'
    assert removed == list(reversed(old[:2]))
    assert len(backup.discover_complete_backups(root)) == 7


def test_failed_dump_never_prunes_existing_backups(tmp_path):
    root = tmp_path / 'backups'
    root.mkdir()
    existing = [completed_backup(root, day) for day in range(1, 9)]

    def fail(*_args):
        raise backup.BackupError('dump failed')

    with pytest.raises(backup.BackupError, match='dump failed'):
        backup.execute(tmp_path, root, keep=7, dump_creator=fail)

    assert all(path.exists() for path in existing)


def test_retention_ignores_unpaired_files_and_refuses_matching_symlinks(tmp_path):
    root = tmp_path / 'backups'
    root.mkdir()
    orphan = root / 'pcep_db_daily_20261001T010000Z.sql.gz'
    orphan.write_text('incomplete')
    unrelated = root / 'pcep_db_20261001T010000Z.sql.gz'
    unrelated.write_text('deploy backup')

    assert backup.prune_backups(root, keep=7) == []
    assert orphan.exists() and unrelated.exists()

    orphan.unlink()
    orphan.symlink_to(unrelated)
    with pytest.raises(backup.BackupError, match='Unsafe matching daily backup'):
        backup.discover_complete_backups(root)


def test_retention_detects_a_corrupted_complete_backup(tmp_path):
    root = tmp_path / 'backups'
    root.mkdir()
    path = completed_backup(root, 1)
    path.write_text('corrupted after checksum')

    with pytest.raises(backup.BackupError, match='checksum verification failed'):
        backup.discover_complete_backups(root)


@pytest.mark.parametrize('value', [0, 6, 366, 'invalid'])
def test_requires_bounded_daily_retention(value):
    with pytest.raises(Exception, match='keep'):
        backup.keep_count(value)
