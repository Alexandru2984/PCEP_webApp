#!/usr/bin/env python3
"""Report or remove obsolete verified PCEP pre-deploy database backups."""

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import stat


def load_operation_lock():
    path = Path(__file__).with_name('operation_lock.py')
    spec = importlib.util.spec_from_file_location('pcep_operation_lock', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('Cannot load the operation-lock implementation.')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


operation_lock = load_operation_lock()
OperationLockError = operation_lock.OperationLockError
exclusive_operation_lock = operation_lock.exclusive_operation_lock


BACKUP_PATTERN = re.compile(
    r'^pcep_db_(?P<stamp>\d{8}T\d{6}Z)\.sql\.gz$'
)
MINIMUM_BACKUPS = 2
MAXIMUM_BACKUPS = 100
DEFAULT_KEEP = 10


class DeploymentBackupRetentionError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedBackup:
    path: Path
    digest: str
    device: int
    inode: int
    size: int
    mtime_ns: int
    link_count: int


def keep_count(value):
    try:
        count = int(value)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError('keep must be an integer') from error
    if not MINIMUM_BACKUPS <= count <= MAXIMUM_BACKUPS:
        raise argparse.ArgumentTypeError(
            f'keep must be between {MINIMUM_BACKUPS} and {MAXIMUM_BACKUPS}'
        )
    return count


def validate_keep(value):
    try:
        return keep_count(value)
    except argparse.ArgumentTypeError as error:
        raise DeploymentBackupRetentionError(str(error)) from error


def prepare_backup_root(path):
    root = Path(path).absolute()
    try:
        metadata = root.lstat()
    except FileNotFoundError as error:
        raise DeploymentBackupRetentionError(
            f'Backup root does not exist: {root}'
        ) from error
    if not stat.S_ISDIR(metadata.st_mode) or root.is_symlink():
        raise DeploymentBackupRetentionError(
            'Backup root must be a real directory.'
        )
    if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077:
        raise DeploymentBackupRetentionError(
            'Backup root must be owned by the current user and private.'
        )
    return root


def backup_identity(metadata):
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_nlink,
    )


def inspect_backup(root, path):
    root = Path(root).absolute()
    path = Path(path).absolute()
    match = BACKUP_PATTERN.fullmatch(path.name)
    if path.parent != root or match is None:
        raise DeploymentBackupRetentionError(
            f'Refusing an out-of-scope pre-deploy backup: {path}'
        )
    try:
        timestamp = datetime.strptime(
            match.group('stamp'),
            '%Y%m%dT%H%M%SZ',
        ).replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise DeploymentBackupRetentionError(
            f'Pre-deploy backup has an invalid timestamp: {path}'
        ) from error
    if timestamp > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise DeploymentBackupRetentionError(
            f'Pre-deploy backup has a future timestamp: {path}'
        )
    try:
        before = path.lstat()
    except FileNotFoundError as error:
        raise DeploymentBackupRetentionError(
            f'Pre-deploy backup disappeared during review: {path}'
        ) from error
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.geteuid()
        or before.st_mode & 0o077
        or before.st_nlink != 1
    ):
        raise DeploymentBackupRetentionError(
            f'Pre-deploy backup is not a private owned single-link regular file: '
            f'{path}'
        )

    flags = os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0)
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, 'rb') as raw_backup:
            opened = os.fstat(raw_backup.fileno())
            if backup_identity(opened) != backup_identity(before):
                raise DeploymentBackupRetentionError(
                    f'Pre-deploy backup changed while it was opened: {path}'
                )
            digest_builder = hashlib.sha256()
            while chunk := raw_backup.read(1024 * 1024):
                digest_builder.update(chunk)
            raw_backup.seek(0)
            with gzip.GzipFile(fileobj=raw_backup, mode='rb') as decompressed:
                prefix = decompressed.read(512)
                if b'PostgreSQL database dump' not in prefix:
                    raise DeploymentBackupRetentionError(
                        f'Pre-deploy backup lacks the PostgreSQL dump header: {path}'
                    )
                while decompressed.read(1024 * 1024):
                    pass
            after = os.fstat(raw_backup.fileno())
    except (EOFError, gzip.BadGzipFile, OSError) as error:
        raise DeploymentBackupRetentionError(
            f'Pre-deploy backup failed integrity validation: {path}: {error}'
        ) from error
    if backup_identity(after) != backup_identity(opened):
        raise DeploymentBackupRetentionError(
            f'Pre-deploy backup changed during validation: {path}'
        )
    return VerifiedBackup(
        path=path,
        digest=digest_builder.hexdigest(),
        device=after.st_dev,
        inode=after.st_ino,
        size=after.st_size,
        mtime_ns=after.st_mtime_ns,
        link_count=after.st_nlink,
    )


def discover_verified_backups(root):
    root = prepare_backup_root(root)
    matches = [
        entry
        for entry in root.iterdir()
        if BACKUP_PATTERN.fullmatch(entry.name) is not None
    ]
    return sorted(
        (inspect_backup(root, path) for path in matches),
        key=lambda backup: backup.path.name,
        reverse=True,
    )


def retention_plan(root, keep=DEFAULT_KEEP):
    keep = validate_keep(keep)
    root = prepare_backup_root(root)
    verified = discover_verified_backups(root)
    retained = verified[:keep]
    # Remove oldest first so an interruption always preserves the newest set.
    removals = list(reversed(verified[keep:]))
    return {'root': root, 'keep': retained, 'remove': removals}


def fsync_directory(path):
    flags = os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0)
    if hasattr(os, 'O_DIRECTORY'):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def same_verified_backup(expected, current):
    return (
        current.path == expected.path
        and current.digest == expected.digest
        and current.device == expected.device
        and current.inode == expected.inode
        and current.size == expected.size
        and current.mtime_ns == expected.mtime_ns
        and current.link_count == expected.link_count
    )


def apply_plan(plan):
    root = prepare_backup_root(plan['root'])
    removed = []
    for expected in plan['remove']:
        current = inspect_backup(root, expected.path)
        if not same_verified_backup(expected, current):
            raise DeploymentBackupRetentionError(
                f'Pre-deploy backup changed after review: {expected.path}'
            )
        current.path.unlink()
        fsync_directory(root)
        removed.append(current.path)
    return removed


def apply_retention(root, keep=DEFAULT_KEEP):
    plan = retention_plan(root, keep)
    apply_plan(plan)
    return plan


def _execute_unlocked(root, keep=DEFAULT_KEEP, apply=False):
    plan = retention_plan(root, keep)
    print(
        f'{"Applying" if apply else "Dry run:"} keep up to the newest {keep} '
        'verified pre-deploy database backups.'
    )
    print(
        f'pre-deploy backups: keep {len(plan["keep"])}, '
        f'remove {len(plan["remove"])}'
    )
    for backup in plan['keep']:
        print(f'  KEEP   {backup.path} ({backup.digest})')
    for backup in plan['remove']:
        print(f'  REMOVE {backup.path} ({backup.digest})')
    if not apply:
        print('Nothing removed. Re-run with --apply only after reviewing this list.')
        return plan
    removed = apply_plan(plan)
    print(f'Removed {len(removed)} reviewed pre-deploy database backups.')
    return plan


def execute(root, keep=DEFAULT_KEEP, apply=False, lock_root=None):
    try:
        with exclusive_operation_lock('backend-maintenance', root=lock_root):
            return _execute_unlocked(root, keep, apply)
    except OperationLockError as error:
        raise DeploymentBackupRetentionError(str(error)) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--backup-root',
        type=Path,
        default=Path('/home/micu/backups/pcep'),
    )
    parser.add_argument('--keep', type=keep_count, default=DEFAULT_KEEP)
    parser.add_argument(
        '--apply',
        action='store_true',
        help='remove the listed backups; without this flag the command is read-only',
    )
    args = parser.parse_args()
    try:
        execute(args.backup_root, args.keep, args.apply)
    except (DeploymentBackupRetentionError, OSError, ValueError) as error:
        parser.exit(1, f'Pre-deploy backup retention refused: {error}\n')


if __name__ == '__main__':
    main()
