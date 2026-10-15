#!/usr/bin/env python3
"""Publish minimal PCEP recovery and database-security health."""

import argparse
from datetime import date, datetime, timedelta, timezone
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
MAX_OFFSITE_STATUS_BYTES = 512
FUTURE_TOLERANCE = timedelta(minutes=5)
OFFSITE_REMOTE_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
SHA256_PATTERN = re.compile(r'^[0-9a-f]{64}$')


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


def load_installation_verifier():
    path = Path(__file__).with_name('verify_operations_installation.py')
    spec = importlib.util.spec_from_file_location(
        'pcep_operations_installation', path
    )
    if spec is None or spec.loader is None:
        raise OperationsHealthError(
            'Cannot load the operations installation verifier.'
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_nginx_installation_verifier():
    path = Path(__file__).with_name('verify_nginx_installation.py')
    spec = importlib.util.spec_from_file_location(
        'pcep_nginx_installation', path
    )
    if spec is None or spec.loader is None:
        raise OperationsHealthError(
            'Cannot load the Nginx installation verifier.'
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_container_runtime_verifier():
    path = Path(__file__).with_name('verify_container_runtime.py')
    spec = importlib.util.spec_from_file_location(
        'pcep_container_runtime', path
    )
    if spec is None or spec.loader is None:
        raise OperationsHealthError(
            'Cannot load the container runtime verifier.'
        )
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


def read_success_status(path, label, private=False):
    status = Path(path).absolute()
    if status.is_symlink() or not status.is_file():
        raise OperationsHealthError(f'{label} status is unavailable.')
    stat = status.stat()
    forbidden_mode = 0o077 if private else 0o022
    if stat.st_uid != os.getuid() or stat.st_mode & forbidden_mode:
        raise OperationsHealthError(f'{label} status permissions are unsafe.')
    if stat.st_size > MAX_STATUS_BYTES:
        raise OperationsHealthError(f'{label} status is oversized.')
    try:
        payload = json.loads(status.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OperationsHealthError(f'{label} status is invalid.') from error
    if not isinstance(payload, dict) or set(payload) != {'schema', 'completed_at'}:
        raise OperationsHealthError(f'{label} status shape is invalid.')
    if payload['schema'] != 1 or isinstance(payload['schema'], bool):
        raise OperationsHealthError(f'{label} status schema is invalid.')
    return utc_moment(payload['completed_at'], label)


def read_restore_status(path):
    return read_success_status(path, 'Restore success')


def verify_restore_freshness(path, max_age_hours, now):
    moment = read_restore_status(path)
    require_fresh(moment, now, max_age_hours, 'Last isolated restore')
    return moment


def verify_database_security_freshness(path, max_age_hours, now):
    moment = read_success_status(path, 'Database security success', private=True)
    require_fresh(moment, now, max_age_hours, 'Last database security check')
    return moment


def read_offsite_status(path):
    if path is None:
        raise OperationsHealthError('Offsite backup success status is unavailable.')
    status = Path(path).absolute()
    if status.is_symlink() or not status.is_file():
        raise OperationsHealthError('Offsite backup success status is unavailable.')
    details = status.stat()
    if details.st_uid != os.getuid() or details.st_mode & 0o077:
        raise OperationsHealthError('Offsite backup success status permissions are unsafe.')
    if details.st_size > MAX_OFFSITE_STATUS_BYTES:
        raise OperationsHealthError('Offsite backup success status is oversized.')
    try:
        lines = status.read_text().splitlines()
        fields = dict(line.split('=', 1) for line in lines)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise OperationsHealthError('Offsite backup success status is invalid.') from error
    if len(lines) != 4 or set(fields) != {'timestamp', 'backup', 'remote', 'sha256'}:
        raise OperationsHealthError('Offsite backup success status shape is invalid.')
    if BACKUP_PATTERN.fullmatch(fields['backup']) is None:
        raise OperationsHealthError('Offsite backup success status has an invalid backup.')
    if OFFSITE_REMOTE_PATTERN.fullmatch(fields['remote']) is None:
        raise OperationsHealthError('Offsite backup success status has an invalid remote.')
    if SHA256_PATTERN.fullmatch(fields['sha256']) is None:
        raise OperationsHealthError('Offsite backup success status has an invalid digest.')
    return utc_moment(fields['timestamp'], 'Offsite backup success')


def verify_offsite_freshness(path, max_age_hours, now):
    moment = read_offsite_status(path)
    require_fresh(moment, now, max_age_hours, 'Last verified offsite backup')
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
    offsite_status=None,
    offsite_required_after=None,
    offsite_max_age_hours=24,
    database_security_status=None,
    database_security_max_age_hours=2,
    verify_installation=False,
    installation_module=None,
    verify_nginx_installation=False,
    nginx_installation_module=None,
    verify_container_runtime=False,
    container_runtime_module=None,
):
    moment = current_utc(now)
    backup_max_age_hours = bounded_hours(backup_max_age_hours)
    restore_max_age_hours = bounded_hours(restore_max_age_hours)
    offsite_max_age_hours = bounded_hours(offsite_max_age_hours)
    database_security_max_age_hours = bounded_hours(
        database_security_max_age_hours
    )
    if offsite_required_after is not None:
        offsite_required_after = calendar_date(offsite_required_after)
    failures = []
    try:
        verify_backup_freshness(
            backup_root, backup_max_age_hours, moment, backup_module=backup_module
        )
    except OperationsHealthError as error:
        failures.append(str(error))
    if offsite_required_after is not None and moment.date() >= offsite_required_after:
        try:
            verify_offsite_freshness(offsite_status, offsite_max_age_hours, moment)
        except OperationsHealthError as error:
            failures.append(str(error))
    try:
        verify_restore_freshness(restore_status, restore_max_age_hours, moment)
    except OperationsHealthError as error:
        failures.append(str(error))
    if database_security_status is not None:
        try:
            verify_database_security_freshness(
                database_security_status,
                database_security_max_age_hours,
                moment,
            )
        except OperationsHealthError as error:
            failures.append(str(error))
    if verify_installation:
        # Any verifier/import failure is an unhealthy attestation, while the
        # public marker deliberately remains free of installation details.
        try:
            verifier = installation_module or load_installation_verifier()
            verifier.verify_installation()
        except Exception:
            failures.append('Operational installation drift detected.')
    if verify_nginx_installation:
        # Nginx file or activation drift is private; the public marker exposes
        # only the same generic degraded state as every other failed control.
        try:
            verifier = (
                nginx_installation_module
                or load_nginx_installation_verifier()
            )
            verifier.verify_installation()
        except Exception:
            failures.append('Nginx installation drift detected.')
    if verify_container_runtime:
        # Container inspection errors remain in the private service journal;
        # the public marker reveals no runtime metadata or environment values.
        try:
            verifier = (
                container_runtime_module or load_container_runtime_verifier()
            )
            verifier.verify_container_runtime()
        except Exception:
            failures.append('Container runtime drift detected.')

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


def calendar_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise argparse.ArgumentTypeError('deadline must be an ISO calendar date')
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            'deadline must be an ISO calendar date'
        ) from error
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError('deadline must be an ISO calendar date')
    return parsed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-root', type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument(
        '--restore-status', type=Path, default=DEFAULT_RESTORE_STATUS
    )
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--backup-max-age-hours', type=bounded_hours, default=26)
    parser.add_argument('--restore-max-age-hours', type=bounded_hours, default=170)
    parser.add_argument('--offsite-status', type=Path)
    parser.add_argument('--offsite-required-after', type=calendar_date)
    parser.add_argument('--offsite-max-age-hours', type=bounded_hours, default=24)
    parser.add_argument('--database-security-status', type=Path)
    parser.add_argument(
        '--database-security-max-age-hours', type=bounded_hours, default=2
    )
    parser.add_argument('--verify-installation', action='store_true')
    parser.add_argument('--verify-nginx-installation', action='store_true')
    parser.add_argument('--verify-container-runtime', action='store_true')
    args = parser.parse_args()
    try:
        payload = execute(
            args.backup_root,
            args.restore_status,
            args.output,
            args.backup_max_age_hours,
            args.restore_max_age_hours,
            offsite_status=args.offsite_status,
            offsite_required_after=args.offsite_required_after,
            offsite_max_age_hours=args.offsite_max_age_hours,
            database_security_status=args.database_security_status,
            database_security_max_age_hours=(
                args.database_security_max_age_hours
            ),
            verify_installation=args.verify_installation,
            verify_nginx_installation=args.verify_nginx_installation,
            verify_container_runtime=args.verify_container_runtime,
        )
    except (OperationsHealthError, OSError, ValueError) as error:
        parser.exit(1, f'Operations health degraded: {error}\n')
    print(json.dumps(payload, separators=(',', ':'), sort_keys=True))


if __name__ == '__main__':
    main()
