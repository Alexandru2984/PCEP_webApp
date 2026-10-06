import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest


spec = importlib.util.spec_from_file_location(
    'database_offsite_backup',
    Path(__file__).resolve().parents[3] / 'scripts/database_offsite_backup.py',
)
offsite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(offsite)


def complete_backup(root, stamp='20261005T010000Z'):
    backup = root / f'pcep_db_daily_{stamp}.sql.gz'
    backup.write_bytes(b'compressed database backup')
    backup.chmod(0o600)
    checksum = backup.with_name(f'{backup.name}.sha256')
    checksum.write_text(
        f'{hashlib.sha256(backup.read_bytes()).hexdigest()}  {backup.name}\n'
    )
    checksum.chmod(0o600)
    return backup, checksum


def crypt_config(name='pcep-crypt'):
    return f"""
[{name}]
type = crypt
remote = r2:pcep-encrypted/database
password = XXX
password2 = XXX
filename_encryption = standard
directory_name_encryption = true
"""


@pytest.mark.parametrize(
    'value',
    ['', 'remote:', 'remote', 'remote:/root', 'remote:path/', 'remote:a//b', 'remote:a/../b', '-bad:path'],
)
def test_rejects_unsafe_or_non_dedicated_remote_paths(value):
    with pytest.raises(offsite.OffsiteBackupError):
        offsite.parse_remote(value)


def test_accepts_a_dedicated_encrypted_remote_path():
    assert offsite.parse_remote('pcep-crypt:pcep/database/daily') == (
        'pcep-crypt',
        'pcep/database/daily',
    )


def test_backup_freshness_rejects_stale_and_future_timestamps(tmp_path):
    current = datetime(2026, 10, 5, 3, tzinfo=timezone.utc)
    fresh = tmp_path / 'pcep_db_daily_20261005T010000Z.sql.gz'
    offsite.verify_backup_freshness(fresh, 6, current)

    stale = tmp_path / 'pcep_db_daily_20261004T010000Z.sql.gz'
    with pytest.raises(offsite.OffsiteBackupError, match='older than 6 hours'):
        offsite.verify_backup_freshness(stale, 6, current)

    future = tmp_path / 'pcep_db_daily_20261005T040000Z.sql.gz'
    with pytest.raises(offsite.OffsiteBackupError, match='in the future'):
        offsite.verify_backup_freshness(future, 6, current)


@pytest.mark.parametrize('value', [0, 169, 'invalid'])
def test_backup_freshness_window_is_bounded(value):
    with pytest.raises(Exception, match='hours'):
        offsite.bounded_hours(value)


@pytest.mark.parametrize(
    'replacement,message',
    [
        ('type = s3', 'crypt remote'),
        ('filename_encryption = off', 'filename mode'),
        ('directory_name_encryption = false', 'Directory-name'),
        ('password2 =', 'second salt'),
        ('remote = r2:', 'non-root'),
    ],
)
def test_crypt_configuration_is_fail_closed(replacement, message):
    lines = crypt_config().splitlines()
    key = replacement.split('=', 1)[0].strip()
    changed = '\n'.join(
        replacement if line.startswith(f'{key} =') else line for line in lines
    )
    with pytest.raises(offsite.OffsiteBackupError, match=message):
        offsite.parse_redacted_remote(changed, 'pcep-crypt')


def test_backend_diagnostics_fail_preflight():
    calls = []

    def runner(rclone, config, arguments, **_kwargs):
        calls.append((rclone, config, arguments))
        if arguments[:2] == ['config', 'redacted']:
            return SimpleNamespace(stdout=crypt_config(), stderr='', returncode=0)
        raise offsite.OffsiteBackupError(
            'rclone backend emitted a diagnostic: retiring shared client'
        )

    with pytest.raises(offsite.OffsiteBackupError, match='retiring shared client'):
        offsite.validate_crypt_remote(
            'pcep-crypt', 'rclone', Path('/config'), runner
        )
    assert len(calls) == 2


def test_round_trip_uploads_only_verified_pair_without_deleting(tmp_path, monkeypatch):
    backup_root = tmp_path / 'daily'
    backup_root.mkdir(mode=0o700)
    backup, checksum = complete_backup(backup_root)
    config = tmp_path / 'rclone.conf'
    config.write_text(crypt_config())
    config.chmod(0o600)
    remote_objects = {}
    commands = []
    status_root = tmp_path / 'status'
    status_root.mkdir(mode=0o700)
    status = status_root / 'last-success'

    monkeypatch.setattr(
        offsite,
        'validate_crypt_remote',
        lambda *_args, **_kwargs: None,
    )

    def runner(_rclone, _config, arguments, **_kwargs):
        commands.append(arguments)
        assert arguments[0] == 'copyto'
        source, destination = arguments[-2:]
        if source.startswith('pcep-crypt:'):
            Path(destination).write_bytes(remote_objects[source])
        else:
            remote_objects[destination] = Path(source).read_bytes()
        return SimpleNamespace(stdout='', stderr='', returncode=0)

    result = offsite.execute(
        backup_root,
        'pcep-crypt:pcep/database/daily',
        config,
        status_file=status,
        now=datetime(2026, 10, 5, 2, tzinfo=timezone.utc),
        runner=runner,
    )

    assert result == backup
    assert set(remote_objects) == {
        f'pcep-crypt:pcep/database/daily/{backup.name}',
        f'pcep-crypt:pcep/database/daily/{checksum.name}',
    }
    assert len(commands) == 4
    assert all(command[0] == 'copyto' for command in commands)
    assert all(command[0] not in {'delete', 'deletefile', 'purge', 'sync'} for command in commands)
    assert status.stat().st_mode & 0o777 == 0o600
    assert status.read_text() == (
        'timestamp=2026-10-05T02:00:00Z\n'
        f'backup={backup.name}\n'
        'remote=pcep-crypt\n'
        f'sha256={hashlib.sha256(backup.read_bytes()).hexdigest()}\n'
    )


def test_round_trip_rejects_remote_corruption(tmp_path, monkeypatch):
    backup_root = tmp_path / 'daily'
    backup_root.mkdir(mode=0o700)
    complete_backup(backup_root)
    config = tmp_path / 'rclone.conf'
    config.write_text(crypt_config())
    config.chmod(0o600)
    remote_objects = {}
    status_root = tmp_path / 'status'
    status_root.mkdir(mode=0o700)
    status = status_root / 'last-success'
    status.write_text('previous-success\n')

    monkeypatch.setattr(
        offsite,
        'validate_crypt_remote',
        lambda *_args, **_kwargs: None,
    )

    def runner(_rclone, _config, arguments, **_kwargs):
        source, destination = arguments[-2:]
        if source.startswith('pcep-crypt:'):
            content = remote_objects[source]
            if source.endswith('.sql.gz'):
                content = b'tampered remotely'
            Path(destination).write_bytes(content)
        else:
            remote_objects[destination] = Path(source).read_bytes()
        return SimpleNamespace(stdout='', stderr='', returncode=0)

    with pytest.raises(offsite.OffsiteBackupError, match='round-trip checksum'):
        offsite.execute(
            backup_root,
            'pcep-crypt:pcep/database/daily',
            config,
            status_file=status,
            now=datetime(2026, 10, 5, 2, tzinfo=timezone.utc),
            runner=runner,
        )
    assert status.read_text() == 'previous-success\n'


@pytest.mark.parametrize('mode', [0o640, 0o606])
def test_config_requires_private_real_file(tmp_path, mode):
    config = tmp_path / 'rclone.conf'
    config.write_text(crypt_config())
    config.chmod(mode)
    with pytest.raises(offsite.OffsiteBackupError, match='mode 0600'):
        offsite.validate_rclone_config(config)

    target = tmp_path / 'real.conf'
    shutil.copyfile(config, target)
    config.unlink()
    config.symlink_to(target)
    with pytest.raises(offsite.OffsiteBackupError, match='real file'):
        offsite.validate_rclone_config(config)


def test_success_status_rejects_unsafe_directory_and_symlink(tmp_path):
    backup = tmp_path / 'pcep_db_daily_20261005T010000Z.sql.gz'
    status_root = tmp_path / 'status'
    status_root.mkdir(mode=0o770)
    # mkdir applies the process umask; force the unsafe mode so this assertion
    # behaves identically on developer machines and hosted CI runners.
    status_root.chmod(0o770)
    status = status_root / 'last-success'
    current = datetime(2026, 10, 5, 2, tzinfo=timezone.utc)

    with pytest.raises(offsite.OffsiteBackupError, match='not writable'):
        offsite.write_success_status(
            status, backup, 'pcep-crypt', 'a' * 64, current
        )

    status_root.chmod(0o700)
    target = status_root / 'target'
    target.write_text('old status')
    status.symlink_to(target)
    with pytest.raises(offsite.OffsiteBackupError, match='real file'):
        offsite.write_success_status(
            status, backup, 'pcep-crypt', 'a' * 64, current
        )


def test_preflight_does_not_transfer_data(tmp_path, monkeypatch):
    backup_root = tmp_path / 'daily'
    backup_root.mkdir(mode=0o700)
    backup, _checksum = complete_backup(backup_root)
    config = tmp_path / 'rclone.conf'
    config.write_text(crypt_config())
    config.chmod(0o600)
    validated = []

    monkeypatch.setattr(
        offsite,
        'validate_crypt_remote',
        lambda name, *_args, **_kwargs: validated.append(name),
    )

    assert offsite.execute(
        backup_root,
        'pcep-crypt:pcep/database/daily',
        config,
        preflight_only=True,
        now=datetime(2026, 10, 5, 2, tzinfo=timezone.utc),
        runner=lambda *_args, **_kwargs: pytest.fail('no transfer expected'),
    ) == backup
    assert validated == ['pcep-crypt']
