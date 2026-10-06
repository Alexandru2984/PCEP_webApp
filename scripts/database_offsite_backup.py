#!/usr/bin/env python3
"""Copy the newest verified PCEP backup through an encrypted rclone remote."""

import argparse
import configparser
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import uuid


DEFAULT_BACKUP_ROOT = Path('/home/micu/backups/pcep/daily')
REMOTE_NAME_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
REMOTE_SEGMENT_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')
BACKUP_STAMP_PATTERN = re.compile(
    r'^pcep_db_daily_(\d{8}T\d{6}Z)\.sql\.gz$'
)


class OffsiteBackupError(RuntimeError):
    pass


def load_database_backup():
    path = Path(__file__).with_name('database_backup.py')
    spec = importlib.util.spec_from_file_location('pcep_database_backup', path)
    if spec is None or spec.loader is None:
        raise OffsiteBackupError('Cannot load the verified backup implementation.')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_rclone_config(path):
    config_path = Path(path).absolute()
    if config_path.is_symlink() or not config_path.is_file():
        raise OffsiteBackupError('rclone config must be a real file.')
    stat = config_path.stat()
    if stat.st_uid != os.getuid():
        raise OffsiteBackupError('rclone config must be owned by the invoking user.')
    if stat.st_mode & 0o077:
        raise OffsiteBackupError('rclone config must have mode 0600 or stricter.')
    return config_path


def parse_remote(value):
    if not value or value.count(':') != 1:
        raise OffsiteBackupError('Remote must use the form crypt-name:dedicated/path.')
    name, path = value.split(':', 1)
    if not REMOTE_NAME_PATTERN.fullmatch(name):
        raise OffsiteBackupError('Remote name contains unsafe characters.')
    if not path or path.startswith('/') or path.endswith('/') or '//' in path:
        raise OffsiteBackupError('Remote path must be a non-root relative path.')
    segments = PurePosixPath(path).parts
    if not segments or any(
        segment in {'.', '..'} or not REMOTE_SEGMENT_PATTERN.fullmatch(segment)
        for segment in segments
    ):
        raise OffsiteBackupError('Remote path contains an unsafe segment.')
    return name, path


def run_rclone(rclone, config_path, arguments, *, timeout=900):
    command = [rclone, '--config', str(config_path), *arguments]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as error:
        raise OffsiteBackupError(f'rclone executable is missing: {rclone}') from error
    except subprocess.TimeoutExpired as error:
        raise OffsiteBackupError(f'rclone command timed out: {arguments[0]}') from error
    if result.returncode:
        detail = result.stderr.strip()[-4000:] or result.stdout.strip()[-4000:]
        raise OffsiteBackupError(
            f'rclone {arguments[0]} failed ({result.returncode}): {detail}'
        )
    if result.stderr.strip():
        raise OffsiteBackupError(
            f'rclone {arguments[0]} emitted a diagnostic: '
            f'{result.stderr.strip()[-4000:]}'
        )
    return result


def parse_redacted_remote(config_text, remote_name):
    parser = configparser.RawConfigParser(interpolation=None)
    try:
        parser.read_string(config_text)
    except configparser.Error as error:
        raise OffsiteBackupError('Cannot parse redacted rclone configuration.') from error
    if not parser.has_section(remote_name):
        raise OffsiteBackupError('Encrypted rclone remote is not configured.')
    section = parser[remote_name]
    if section.get('type') != 'crypt':
        raise OffsiteBackupError('Offsite destination must be an rclone crypt remote.')
    if section.get('filename_encryption') != 'standard':
        raise OffsiteBackupError('Encrypted filename mode must be explicitly standard.')
    if section.get('directory_name_encryption') != 'true':
        raise OffsiteBackupError('Directory-name encryption must be explicitly enabled.')
    if not section.get('password') or not section.get('password2'):
        raise OffsiteBackupError('The crypt remote requires a password and second salt.')

    wrapped = section.get('remote', '')
    try:
        wrapped_name, _wrapped_path = parse_remote(wrapped)
    except OffsiteBackupError as error:
        raise OffsiteBackupError(
            'The crypt remote must wrap a dedicated non-root path with safe segments.'
        ) from error
    if wrapped_name == remote_name:
        raise OffsiteBackupError('The crypt remote must not wrap itself.')


def validate_crypt_remote(remote_name, rclone, config_path, runner=run_rclone):
    redacted = runner(
        rclone,
        config_path,
        ['config', 'redacted', remote_name],
        timeout=30,
    )
    parse_redacted_remote(redacted.stdout, remote_name)
    features = runner(
        rclone,
        config_path,
        ['backend', 'features', f'{remote_name}:', '--json'],
        timeout=60,
    )
    try:
        feature_data = json.loads(features.stdout)
    except json.JSONDecodeError as error:
        raise OffsiteBackupError('rclone backend features returned invalid JSON.') from error
    if not str(feature_data.get('String', '')).startswith('Encrypted '):
        raise OffsiteBackupError('rclone did not instantiate an encrypted backend.')


def latest_backup(backup_root, backup_module):
    root = Path(backup_root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise OffsiteBackupError('Backup root must be a real directory.')
    if root.stat().st_mode & 0o077:
        raise OffsiteBackupError('Backup root must not be accessible by group or others.')
    try:
        complete = backup_module.discover_complete_backups(root)
    except (OSError, backup_module.BackupError) as error:
        raise OffsiteBackupError(f'Cannot verify daily backups: {error}') from error
    if not complete:
        raise OffsiteBackupError('No complete verified daily backup is available.')
    return complete[0]


def bounded_hours(value):
    try:
        hours = int(value)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError('hours must be an integer') from error
    if not 1 <= hours <= 168:
        raise argparse.ArgumentTypeError('hours must be between 1 and 168')
    return hours


def verify_backup_freshness(backup, max_age_hours, now=None):
    match = BACKUP_STAMP_PATTERN.fullmatch(Path(backup).name)
    if not match:
        raise OffsiteBackupError('Backup filename has no valid UTC timestamp.')
    created = datetime.strptime(match.group(1), '%Y%m%dT%H%M%SZ').replace(
        tzinfo=timezone.utc
    )
    moment = now or datetime.now(timezone.utc)
    age_seconds = (moment.astimezone(timezone.utc) - created).total_seconds()
    if age_seconds < -300:
        raise OffsiteBackupError('Newest backup timestamp is unexpectedly in the future.')
    if age_seconds > max_age_hours * 3600:
        raise OffsiteBackupError(
            f'Newest verified backup is older than {max_age_hours} hours.'
        )


def remote_file(remote, filename):
    return f'{remote}/{filename}'


def upload_command(source, destination):
    return [
        'copyto',
        '--immutable',
        '--no-traverse',
        '--retries',
        '3',
        '--low-level-retries',
        '10',
        '--contimeout',
        '15s',
        '--timeout',
        '5m',
        str(source),
        destination,
    ]


def download_command(source, destination):
    return [
        'copyto',
        '--retries',
        '3',
        '--low-level-retries',
        '10',
        '--contimeout',
        '15s',
        '--timeout',
        '5m',
        source,
        str(destination),
    ]


def write_success_status(path, backup, remote_name, digest, now):
    if path is None:
        return
    status = Path(path).absolute()
    parent = status.parent
    if parent.is_symlink() or not parent.is_dir():
        raise OffsiteBackupError('Status directory must be a real directory.')
    parent_stat = parent.stat()
    if parent_stat.st_uid != os.getuid() or parent_stat.st_mode & 0o022:
        raise OffsiteBackupError(
            'Status directory must be owned by the invoking user and not writable '
            'by group or others.'
        )
    if status.exists() or status.is_symlink():
        if status.is_symlink() or not status.is_file():
            raise OffsiteBackupError('Existing status path must be a real file.')
        if status.stat().st_uid != os.getuid():
            raise OffsiteBackupError('Existing status file has the wrong owner.')

    temporary = parent / f'.{status.name}.partial-{uuid.uuid4().hex}'
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, 'w') as output:
            timestamp = now.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            output.write(f'timestamp={timestamp}\n')
            output.write(f'backup={backup.name}\n')
            output.write(f'remote={remote_name}\n')
            output.write(f'sha256={digest}\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, status)
        status.chmod(0o600)
        directory = os.open(parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def execute(
    backup_root,
    remote,
    rclone_config,
    *,
    rclone='rclone',
    preflight_only=False,
    max_age_hours=48,
    status_file=None,
    now=None,
    runner=run_rclone,
):
    remote_name, _remote_path = parse_remote(remote)
    config_path = validate_rclone_config(rclone_config)
    moment = now or datetime.now(timezone.utc)
    backup_module = load_database_backup()
    backup, checksum = latest_backup(backup_root, backup_module)
    verify_backup_freshness(backup, bounded_hours(max_age_hours), moment)
    validate_crypt_remote(remote_name, rclone, config_path, runner)

    if preflight_only:
        print(f'Encrypted offsite preflight passed for {remote_name}.')
        print(f'Newest verified local backup: {backup.name}')
        return backup

    remote_backup = remote_file(remote, backup.name)
    remote_checksum = remote_file(remote, checksum.name)
    runner(rclone, config_path, upload_command(backup, remote_backup))
    runner(rclone, config_path, upload_command(checksum, remote_checksum))

    with tempfile.TemporaryDirectory(prefix='pcep-offsite-verify-') as temporary:
        verification_root = Path(temporary)
        verification_root.chmod(0o700)
        downloaded_backup = verification_root / backup.name
        downloaded_checksum = verification_root / checksum.name
        runner(
            rclone,
            config_path,
            download_command(remote_backup, downloaded_backup),
        )
        runner(
            rclone,
            config_path,
            download_command(remote_checksum, downloaded_checksum),
        )
        downloaded_backup.chmod(0o600)
        downloaded_checksum.chmod(0o600)
        try:
            backup_module.verify_checksum(downloaded_backup, downloaded_checksum)
        except (OSError, backup_module.BackupError) as error:
            raise OffsiteBackupError(
                f'Offsite round-trip checksum verification failed: {error}'
            ) from error
        if backup_module.file_sha256(backup) != backup_module.file_sha256(
            downloaded_backup
        ):
            raise OffsiteBackupError('Offsite round-trip content does not match locally.')

    backup_module.verify_checksum(backup, checksum)
    digest = backup_module.file_sha256(backup)
    write_success_status(status_file, backup, remote_name, digest, moment)
    print(f'Encrypted offsite backup verified: {backup.name}')
    print(f'Encrypted rclone remote: {remote_name}')
    print('Remote retention was not changed.')
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-root', type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument('--remote', default=os.environ.get('PCEP_OFFSITE_REMOTE'))
    parser.add_argument(
        '--rclone-config',
        type=Path,
        default=os.environ.get('PCEP_RCLONE_CONFIG'),
    )
    parser.add_argument('--rclone', default='rclone')
    parser.add_argument('--max-age-hours', type=bounded_hours, default=48)
    parser.add_argument('--status-file', type=Path)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    if not args.remote:
        parser.error('--remote or PCEP_OFFSITE_REMOTE is required')
    if not args.rclone_config:
        parser.error('--rclone-config or PCEP_RCLONE_CONFIG is required')
    try:
        execute(
            args.backup_root,
            args.remote,
            args.rclone_config,
            rclone=args.rclone,
            preflight_only=args.preflight_only,
            max_age_hours=args.max_age_hours,
            status_file=args.status_file,
        )
    except (OffsiteBackupError, OSError, ValueError) as error:
        parser.exit(1, f'Offsite database backup failed: {error}\n')


if __name__ == '__main__':
    main()
