#!/usr/bin/env python3
"""Create and retain verified daily PostgreSQL backups for PCEP."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import uuid


DAILY_PREFIX = 'pcep_db_daily'
DAILY_PATTERN = re.compile(r'^pcep_db_daily_\d{8}T\d{6}Z\.sql\.gz$')


class BackupError(RuntimeError):
    pass


def keep_count(value):
    try:
        count = int(value)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError('keep must be an integer') from error
    if not 7 <= count <= 365:
        raise argparse.ArgumentTypeError('keep must be between 7 and 365')
    return count


def prepare_backup_root(path):
    root = Path(path).absolute()
    if root.is_symlink():
        raise BackupError('Backup root must not be a symlink.')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not root.is_dir():
        raise BackupError('Backup root must be a real directory.')
    root.chmod(0o700)
    return root


@contextmanager
def exclusive_backup_lock(root):
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(root / '.database-backup.lock', flags, 0o600)
    except OSError as error:
        raise BackupError(f'Cannot open the database backup lock: {error}') from error
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise BackupError('Another database backup is already running.') from error
        yield
    finally:
        os.close(descriptor)


def load_deploy_backend():
    path = Path(__file__).with_name('deploy_backend.py')
    spec = importlib.util.spec_from_file_location('pcep_deploy_backend', path)
    if spec is None or spec.loader is None:
        raise BackupError('Cannot load the verified database backup implementation.')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_dump(project_root, backup_root, container, stamp):
    deploy = load_deploy_backend()
    config = deploy.ReleaseConfig(
        project_root=project_root,
        backup_root=backup_root,
        release='scheduled-backup',
        public_health_url='https://invalid.example',
        database_container=container,
    )
    return deploy.backup_database(config, stamp, filename_prefix=DAILY_PREFIX)


def checksum_path(backup):
    return backup.with_name(f'{backup.name}.sha256')


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fsync_directory(path):
    flags = os.O_RDONLY
    if hasattr(os, 'O_DIRECTORY'):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_checksum(backup, digest):
    final = checksum_path(backup)
    if final.exists() or final.is_symlink():
        raise BackupError(f'Checksum already exists: {final}')
    partial = final.with_name(f'.{final.name}.partial-{uuid.uuid4().hex}')
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'w') as output:
            output.write(f'{digest}  {backup.name}\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(partial, final)
        final.chmod(0o600)
        fsync_directory(final.parent)
    finally:
        partial.unlink(missing_ok=True)
    return final


def verify_checksum(backup, checksum):
    if backup.stat().st_mode & 0o077 or checksum.stat().st_mode & 0o077:
        raise BackupError(f'Daily backup or checksum is not private: {backup}')
    if checksum.stat().st_size > 256:
        raise BackupError(f'Invalid daily backup checksum file: {checksum}')
    expected = f'{file_sha256(backup)}  {backup.name}\n'
    if checksum.read_text() != expected:
        raise BackupError(f'Daily backup checksum verification failed: {backup}')


def discover_complete_backups(root):
    complete = []
    for backup in root.iterdir():
        if not DAILY_PATTERN.fullmatch(backup.name):
            continue
        if backup.is_symlink() or not backup.is_file():
            raise BackupError(f'Unsafe matching daily backup: {backup}')
        checksum = checksum_path(backup)
        if checksum.is_symlink():
            raise BackupError(f'Unsafe matching checksum: {checksum}')
        if checksum.is_file():
            verify_checksum(backup, checksum)
            complete.append((backup, checksum))
    return sorted(complete, key=lambda pair: pair[0].name, reverse=True)


def prune_backups(root, keep):
    complete = discover_complete_backups(root)
    removed = []
    for backup, checksum in complete[keep:]:
        checksum.unlink()
        backup.unlink()
        removed.append(backup)
    if removed:
        fsync_directory(root)
    return removed


def execute(
    project_root,
    backup_root,
    container='pcep_db',
    keep=30,
    now=None,
    dump_creator=create_dump,
):
    keep = keep_count(keep)
    project_root = Path(project_root).resolve()
    if not project_root.is_dir():
        raise BackupError('Project root must be a real directory.')
    root = prepare_backup_root(backup_root)
    moment = now or datetime.now(timezone.utc)
    stamp = moment.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

    with exclusive_backup_lock(root):
        backup, digest = dump_creator(project_root, root, container, stamp)
        backup = Path(backup)
        if backup.parent != root or not DAILY_PATTERN.fullmatch(backup.name):
            raise BackupError('Backup implementation returned an unexpected path.')
        if not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise BackupError('Backup implementation returned an invalid checksum.')
        with backup.open('rb') as source:
            os.fsync(source.fileno())
        checksum = write_checksum(backup, digest)
        removed = prune_backups(root, keep)

    print(f'Verified database backup: {backup}')
    print(f'Database backup SHA-256: {digest}')
    print(f'Checksum file: {checksum}')
    retained = len(discover_complete_backups(root))
    print(f'Retained {retained} daily backups; removed {len(removed)}.')
    return backup, digest, removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--project-root',
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        '--backup-root',
        type=Path,
        default=Path('/home/micu/backups/pcep/daily'),
    )
    parser.add_argument('--container', default='pcep_db')
    parser.add_argument('--keep', type=keep_count, default=30)
    args = parser.parse_args()
    try:
        execute(args.project_root, args.backup_root, args.container, args.keep)
    except (BackupError, OSError, ValueError) as error:
        parser.exit(1, f'Database backup failed: {error}\n')


if __name__ == '__main__':
    main()
