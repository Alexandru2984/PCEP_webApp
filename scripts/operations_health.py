#!/usr/bin/env python3
"""Publish a minimal public attestation of PCEP backup and restore freshness."""

import argparse
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import uuid


DEFAULT_BACKUP_ROOT = Path('/home/micu/backups/pcep/daily')
DEFAULT_RESTORE_STATUS = Path('/var/lib/pcep-db-restore-check/last-success.json')
DEFAULT_OUTPUT = Path('/var/lib/pcep-operations-health/status.json')
BACKUP_PATTERN = re.compile(r'^pcep_db_daily_(\d{8}T\d{6}Z)\.sql\.gz$')
UTC_TIMESTAMP_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
MAX_STATUS_BYTES = 256
FUTURE_TOLERANCE = timedelta(minutes=5)


class OperationsHealthError(RuntimeError):
    pass


def load_database_backup():
    path = Path(__file__).with_name('database_backup.py')
    spec = importlib.util.spec_from_file_location('pcep_database_backup', path)
    if spec is None or spec.loader is None:
        raise OperationsHealthError('Cannot load the verified backup implementation.')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def utc_moment(value, label):
    if not isinstance(value, str) or not UTC_TIMESTAMP_PATTERN.fullmatch(value):
        raise OperationsHealthError(f'{label} timestamp is invalid.')
    try:
        return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(
            tzinfo=timezone.utc
        )
    except ValueError as error:
        raise OperationsHealthError(f'{label} timestamp is invalid.') from error


def current_utc(now=None):
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise OperationsHealthError('Current time must include a timezone.')
    return moment.astimezone(timezone.utc)


def require_fresh(moment, now, max_age_hours, label):
    age = now - moment
    if age < -FUTURE_TOLERANCE:
        raise OperationsHealthError(f'{label} timestamp is unexpectedly in the future.')
    if age > timedelta(hours=max_age_hours):
        raise OperationsHealthError(f'{label} is stale.')


def verify_backup_freshness(backup_root, max_age_hours, now, backup_module=None):
    root = Path(backup_root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise OperationsHealthError('Backup root must be a real directory.')
    if root.stat().st_mode & 0o077:
        raise OperationsHealthError('Backup root must remain private.')
    backup_module = backup_module or load_database_backup()
    try:
        complete = backup_module.discover_complete_backups(root)
    except (OSError, backup_module.BackupError) as error:
        raise OperationsHealthError('A local backup failed integrity validation.') from error
    if not complete:
        raise OperationsHealthError('No complete verified local backup is available.')
    match = BACKUP_PATTERN.fullmatch(complete[0][0].name)
    if match is None:
        raise OperationsHealthError('Newest backup has an invalid timestamp.')
    moment = datetime.strptime(match.group(1), '%Y%m%dT%H%M%SZ').replace(
        tzinfo=timezone.utc
    )
    require_fresh(moment, now, max_age_hours, 'Newest verified backup')
    return moment


def read_restore_status(path):
    status = Path(path).absolute()
    if status.is_symlink() or not status.is_file():
        raise OperationsHealthError('Restore success status is unavailable.')
    stat = status.stat()
    if stat.st_uid != os.getuid() or stat.st_mode & 0o022:
        raise OperationsHealthError('Restore success status permissions are unsafe.')
    if stat.st_size > MAX_STATUS_BYTES:
        raise OperationsHealthError('Restore success status is oversized.')
    try:
        payload = json.loads(status.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OperationsHealthError('Restore success status is invalid.') from error
    if not isinstance(payload, dict) or set(payload) != {'schema', 'completed_at'}:
        raise OperationsHealthError('Restore success status shape is invalid.')
    if payload['schema'] != 1 or isinstance(payload['schema'], bool):
        raise OperationsHealthError('Restore success status schema is invalid.')
    return utc_moment(payload['completed_at'], 'Restore success')


def verify_restore_freshness(path, max_age_hours, now):
    moment = read_restore_status(path)
    require_fresh(moment, now, max_age_hours, 'Last isolated restore')
    return moment


def write_public_status(path, status, now):
    if status not in {'ok', 'degraded'}:
        raise OperationsHealthError('Public operations status is invalid.')
    output_path = Path(path).absolute()
    parent = output_path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise OperationsHealthError('Public status directory must be a real directory.')
    parent_stat = parent.stat()
    if parent_stat.st_uid != os.getuid() or parent_stat.st_mode & 0o022:
        raise OperationsHealthError(
            'Public status directory must be owned by the invoking user and not '
            'writable by group or others.'
        )
    if output_path.exists() or output_path.is_symlink():
        if output_path.is_symlink() or not output_path.is_file():
            raise OperationsHealthError('Existing public status must be a real file.')
        if output_path.stat().st_uid != os.getuid():
            raise OperationsHealthError('Existing public status has the wrong owner.')

    payload = {
        'checked_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'schema': 1,
        'status': status,
    }
    temporary = parent / f'.{output_path.name}.partial-{uuid.uuid4().hex}'
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, 'w') as output:
            json.dump(payload, output, separators=(',', ':'), sort_keys=True)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, output_path)
        output_path.chmod(0o600)
        directory = os.open(parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
    return payload


def execute(
    backup_root,
    restore_status,
    output,
    backup_max_age_hours=26,
    restore_max_age_hours=170,
    now=None,
    backup_module=None,
):
    moment = current_utc(now)
    backup_max_age_hours = bounded_hours(backup_max_age_hours)
    restore_max_age_hours = bounded_hours(restore_max_age_hours)
    failures = []
    try:
        verify_backup_freshness(
            backup_root, backup_max_age_hours, moment, backup_module=backup_module
        )
    except OperationsHealthError as error:
        failures.append(str(error))
    try:
        verify_restore_freshness(restore_status, restore_max_age_hours, moment)
    except OperationsHealthError as error:
        failures.append(str(error))

    payload = write_public_status(output, 'degraded' if failures else 'ok', moment)
    if failures:
        raise OperationsHealthError(' '.join(failures))
    return payload


def bounded_hours(value):
    try:
        hours = int(value)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError('age must be an integer number of hours') from error
    if not 1 <= hours <= 336:
        raise argparse.ArgumentTypeError('age must be between 1 and 336 hours')
    return hours


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-root', type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument(
        '--restore-status', type=Path, default=DEFAULT_RESTORE_STATUS
    )
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--backup-max-age-hours', type=bounded_hours, default=26)
    parser.add_argument('--restore-max-age-hours', type=bounded_hours, default=170)
    args = parser.parse_args()
    try:
        payload = execute(
            args.backup_root,
            args.restore_status,
            args.output,
            args.backup_max_age_hours,
            args.restore_max_age_hours,
        )
    except (OperationsHealthError, OSError, ValueError) as error:
        parser.exit(1, f'Operations health degraded: {error}\n')
    print(json.dumps(payload, separators=(',', ':'), sort_keys=True))


if __name__ == '__main__':
    main()
