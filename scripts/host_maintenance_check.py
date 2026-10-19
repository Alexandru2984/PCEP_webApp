#!/usr/bin/env python3
"""Prove PCEP readiness immediately before and after a reviewed host reboot."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import secrets
import stat
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BOOT_ID_PATH = Path('/proc/sys/kernel/random/boot_id')
BOOT_ROOT = Path('/boot')
REBOOT_REQUIRED_PATH = Path('/var/run/reboot-required')
STATE_NAME_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')
BOOT_ID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
)
KERNEL_PATTERN = re.compile(
    r'^(?P<major>[0-9]+)\.(?P<minor>[0-9]+)\.(?P<patch>[0-9]+)-'
    r'(?P<build>[0-9]+)-(?P<flavour>[a-z0-9._-]+)$'
)
COMMIT_PATTERN = re.compile(r'^[0-9a-f]{40}$')
MAX_STATE_BYTES = 4096
PCEP_SERVICES = (
    'pcep-analytics-retention.service',
    'pcep-database-security.service',
    'pcep-db-backup.service',
    'pcep-db-restore-check.service',
    'pcep-operations-health.service',
    'pcep-seo-pages.service',
)
HOST_SERVICES = ('nginx.service', 'docker.service', 'cloudflared.service')
SNAPSHOT_KEYS = {
    'boot_id',
    'checked_at',
    'expected_kernel',
    'reboot_required',
    'repository_commit',
    'running_kernel',
}


class HostMaintenanceError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        '+00:00', 'Z'
    )


def run_process(command, *, cwd=None, timeout=180):
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise HostMaintenanceError(
            f'Cannot run required check {Path(command[0]).name}.'
        ) from error


def require_success(command, label, *, cwd=None, timeout=180, runner=run_process):
    result = runner(command, cwd=cwd, timeout=timeout)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or '').strip().splitlines()
        suffix = f': {detail[-1][:300]}' if detail else ''
        raise HostMaintenanceError(f'{label} failed{suffix}')
    return result.stdout.strip()


def git_revision(project_root=PROJECT_ROOT, *, runner=run_process):
    root = str(Path(project_root).resolve())
    branch = require_success(
        ['/usr/bin/git', '-C', root, 'symbolic-ref', '--short', 'HEAD'],
        'Repository branch check',
        runner=runner,
    )
    if branch != 'main':
        raise HostMaintenanceError('Host maintenance must run from the main branch.')
    dirty = require_success(
        [
            '/usr/bin/git',
            '-C',
            root,
            'status',
            '--porcelain',
            '--untracked-files=no',
        ],
        'Repository worktree check',
        runner=runner,
    )
    if dirty:
        raise HostMaintenanceError(
            'Tracked repository files must be clean before host maintenance.'
        )
    head = require_success(
        ['/usr/bin/git', '-C', root, 'rev-parse', 'HEAD'],
        'Repository revision check',
        runner=runner,
    )
    upstream = require_success(
        ['/usr/bin/git', '-C', root, 'rev-parse', 'origin/main'],
        'Repository upstream check',
        runner=runner,
    )
    remote_output = require_success(
        [
            '/usr/bin/git',
            '-C',
            root,
            'ls-remote',
            '--exit-code',
            'origin',
            'refs/heads/main',
        ],
        'Repository remote main check',
        runner=runner,
    )
    remote_fields = remote_output.split()
    if (
        len(remote_fields) != 2
        or remote_fields[1] != 'refs/heads/main'
        or COMMIT_PATTERN.fullmatch(remote_fields[0]) is None
    ):
        raise HostMaintenanceError('Remote main response is invalid.')
    if (
        head != upstream
        or head != remote_fields[0]
        or COMMIT_PATTERN.fullmatch(head) is None
    ):
        raise HostMaintenanceError(
            'Local main must exactly match both fetched and live origin/main.'
        )
    return head


def read_boot_id(path=BOOT_ID_PATH):
    value = Path(path).read_text(encoding='ascii').strip()
    if BOOT_ID_PATTERN.fullmatch(value) is None:
        raise HostMaintenanceError('Kernel boot ID is invalid.')
    return value


def kernel_key(value):
    match = KERNEL_PATTERN.fullmatch(value)
    if match is None:
        raise HostMaintenanceError(f'Unsupported kernel release: {value}')
    return (
        int(match['major']),
        int(match['minor']),
        int(match['patch']),
        int(match['build']),
        match['flavour'],
    )


def newest_installed_kernel(
    running_kernel=None,
    boot_root=BOOT_ROOT,
    *,
    expected_uid=0,
):
    running = running_kernel or platform.release()
    running_match = KERNEL_PATTERN.fullmatch(running)
    if running_match is None:
        raise HostMaintenanceError(f'Unsupported running kernel release: {running}')
    candidates = []
    for path in Path(boot_root).glob('vmlinuz-*'):
        release = path.name.removeprefix('vmlinuz-')
        match = KERNEL_PATTERN.fullmatch(release)
        if match is None or match['flavour'] != running_match['flavour']:
            continue
        if path.is_symlink():
            raise HostMaintenanceError(f'Installed kernel image is a symlink: {path}')
        details = path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != expected_uid
            or details.st_mode & 0o022
        ):
            raise HostMaintenanceError(
                f'Installed kernel image has unsafe metadata: {path}'
            )
        candidates.append(release)
    if not candidates:
        raise HostMaintenanceError(
            'No trusted installed kernel image matches the running kernel flavour.'
        )
    return max(candidates, key=kernel_key)


def require_service_state(*, runner=run_process):
    for service in HOST_SERVICES:
        require_success(
            ['/usr/bin/systemctl', 'is-active', '--quiet', service],
            f'Required host service {service}',
            timeout=15,
            runner=runner,
        )
    for service in PCEP_SERVICES:
        active = require_success(
            [
                '/usr/bin/systemctl',
                'show',
                '--property=ActiveState',
                '--value',
                service,
            ],
            f'PCEP service state query for {service}',
            timeout=15,
            runner=runner,
        )
        if active != 'inactive':
            raise HostMaintenanceError(
                f'PCEP service must be quiescent before the proof: {service}={active}'
            )
        failed = runner(
            ['/usr/bin/systemctl', 'is-failed', '--quiet', service],
            timeout=15,
        )
        if failed.returncode == 0:
            raise HostMaintenanceError(f'PCEP service is failed: {service}')
        if failed.returncode != 1:
            raise HostMaintenanceError(
                f'Cannot query the failure state of PCEP service: {service}'
            )


def run_live_checks(project_root=PROJECT_ROOT, *, runner=run_process):
    project_root = Path(project_root).resolve()
    revision = git_revision(project_root, runner=runner)
    # Preserve the virtual-environment entry path. Resolving its interpreter
    # symlink would bypass pyvenv.cfg and lose the audited dependencies.
    python = sys.executable
    scripts = project_root / 'scripts'
    checks = (
        (
            [python, str(scripts / 'verify_nginx_installation.py')],
            'Nginx installation verification',
        ),
        (
            [python, str(scripts / 'verify_operations_installation.py')],
            'Operations installation verification',
        ),
        (
            [python, str(scripts / 'verify_container_runtime.py')],
            'Container runtime verification',
        ),
        (
            [
                python,
                str(scripts / 'production_smoke.py'),
                '--base-url',
                'https://pcep.micutu.com',
                '--runner-url',
                'https://pcep-runner.micutu.com',
            ],
            'External production smoke',
        ),
    )
    for command, label in checks:
        require_success(
            command,
            label,
            cwd=str(project_root),
            runner=runner,
        )
    require_service_state(runner=runner)
    return revision


def snapshot(
    revision,
    *,
    boot_id_path=BOOT_ID_PATH,
    boot_root=BOOT_ROOT,
    reboot_required_path=REBOOT_REQUIRED_PATH,
    running_kernel=None,
    expected_uid=0,
):
    running = running_kernel or platform.release()
    expected = newest_installed_kernel(
        running,
        boot_root,
        expected_uid=expected_uid,
    )
    return {
        'boot_id': read_boot_id(boot_id_path),
        'checked_at': utc_now(),
        'expected_kernel': expected,
        'reboot_required': Path(reboot_required_path).exists(),
        'repository_commit': revision,
        'running_kernel': running,
    }


def state_parent(path, *, expected_uid=None):
    target = Path(path).absolute()
    if STATE_NAME_PATTERN.fullmatch(target.name) is None:
        raise HostMaintenanceError('Maintenance state filename is unsafe.')
    parent = target.parent
    if parent.is_symlink() or parent.resolve() != parent:
        raise HostMaintenanceError(
            'Maintenance state parent must not contain a symlink.'
        )
    details = parent.stat(follow_symlinks=False)
    owner = os.getuid() if expected_uid is None else expected_uid
    if (
        not stat.S_ISDIR(details.st_mode)
        or details.st_uid != owner
        or details.st_mode & 0o022
    ):
        raise HostMaintenanceError(
            'Maintenance state parent must be owner-controlled and not writable by group or others.'
        )
    return target, parent


def encode_state(payload):
    data = (json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n').encode()
    if len(data) > MAX_STATE_BYTES:
        raise HostMaintenanceError('Maintenance state exceeds its size limit.')
    return data


def write_all(descriptor, data):
    written = 0
    while written < len(data):
        count = os.write(descriptor, data[written:])
        if count <= 0:
            raise HostMaintenanceError('Cannot complete the maintenance state write.')
        written += count


def write_state(path, payload, *, replace, expected_uid=None):
    target, parent = state_parent(path, expected_uid=expected_uid)
    directory_flags = os.O_RDONLY
    if hasattr(os, 'O_DIRECTORY'):
        directory_flags |= os.O_DIRECTORY
    if hasattr(os, 'O_NOFOLLOW'):
        directory_flags |= os.O_NOFOLLOW
    directory = os.open(parent, directory_flags)
    temporary_name = f'.{target.name}.{secrets.token_hex(8)}.tmp'
    temporary = None
    try:
        if not replace:
            try:
                existing = os.stat(target.name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                existing = None
            if existing is not None:
                raise HostMaintenanceError(
                    'Maintenance state already exists; use a new evidence filename.'
                )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, 'O_CLOEXEC'):
            flags |= os.O_CLOEXEC
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW
        temporary = os.open(temporary_name, flags, 0o600, dir_fd=directory)
        data = encode_state(payload)
        write_all(temporary, data)
        os.fsync(temporary)
        os.close(temporary)
        temporary = None
        os.replace(
            temporary_name,
            target.name,
            src_dir_fd=directory,
            dst_dir_fd=directory,
        )
        os.fsync(directory)
    finally:
        if temporary is not None:
            os.close(temporary)
        try:
            os.unlink(temporary_name, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.close(directory)


def validate_snapshot(value):
    if not isinstance(value, dict) or set(value) != SNAPSHOT_KEYS:
        raise HostMaintenanceError('Maintenance snapshot schema is invalid.')
    if BOOT_ID_PATTERN.fullmatch(value.get('boot_id', '')) is None:
        raise HostMaintenanceError('Maintenance snapshot boot ID is invalid.')
    for key in ('running_kernel', 'expected_kernel'):
        if not isinstance(value.get(key), str):
            raise HostMaintenanceError('Maintenance snapshot kernel is invalid.')
        kernel_key(value[key])
    if COMMIT_PATTERN.fullmatch(value.get('repository_commit', '')) is None:
        raise HostMaintenanceError('Maintenance snapshot revision is invalid.')
    if not isinstance(value.get('reboot_required'), bool):
        raise HostMaintenanceError('Maintenance snapshot reboot flag is invalid.')
    try:
        checked_at = datetime.fromisoformat(value.get('checked_at', '').replace('Z', '+00:00'))
    except (TypeError, ValueError) as error:
        raise HostMaintenanceError(
            'Maintenance snapshot timestamp is invalid.'
        ) from error
    if checked_at.tzinfo is None:
        raise HostMaintenanceError('Maintenance snapshot timestamp is not UTC-aware.')


def read_state(path, *, expected_uid=None):
    target, parent = state_parent(path, expected_uid=expected_uid)
    directory_flags = os.O_RDONLY
    if hasattr(os, 'O_DIRECTORY'):
        directory_flags |= os.O_DIRECTORY
    if hasattr(os, 'O_NOFOLLOW'):
        directory_flags |= os.O_NOFOLLOW
    directory = os.open(parent, directory_flags)
    descriptor = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, 'O_CLOEXEC'):
            flags |= os.O_CLOEXEC
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(target.name, flags, dir_fd=directory)
        details = os.fstat(descriptor)
        owner = os.getuid() if expected_uid is None else expected_uid
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != owner
            or stat.S_IMODE(details.st_mode) != 0o600
            or details.st_nlink != 1
            or details.st_size > MAX_STATE_BYTES
        ):
            raise HostMaintenanceError(
                'Maintenance state must be a bounded owner-only regular file.'
            )
        chunks = []
        remaining = MAX_STATE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b''.join(chunks)
    except OSError as error:
        raise HostMaintenanceError(f'Cannot read maintenance state: {error}') from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory)
    try:
        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HostMaintenanceError('Maintenance state is not valid JSON.') from error
    if not isinstance(payload, dict) or payload.get('schema') != 1:
        raise HostMaintenanceError('Maintenance state schema is invalid.')
    if payload.get('phase') != 'preflight' or set(payload) != {
        'phase',
        'preflight',
        'schema',
    }:
        raise HostMaintenanceError(
            'Maintenance state is not an unfinished preflight proof.'
        )
    validate_snapshot(payload.get('preflight'))
    return payload


def preflight(state_file, *, project_root=PROJECT_ROOT):
    revision = run_live_checks(project_root)
    evidence = snapshot(revision)
    payload = {'schema': 1, 'phase': 'preflight', 'preflight': evidence}
    write_state(state_file, payload, replace=False)
    return payload


def validate_postflight(before, after):
    validate_snapshot(before)
    validate_snapshot(after)
    if before['boot_id'] == after['boot_id']:
        raise HostMaintenanceError('Boot ID did not change; no reboot was proven.')
    if after['running_kernel'] != before['expected_kernel']:
        raise HostMaintenanceError(
            'Running kernel does not match the preflight expected kernel.'
        )
    if after['expected_kernel'] != before['expected_kernel']:
        raise HostMaintenanceError(
            'Installed kernel inventory changed after the preflight proof.'
        )
    if after['repository_commit'] != before['repository_commit']:
        raise HostMaintenanceError(
            'Repository revision changed during host maintenance.'
        )
    if after['reboot_required']:
        raise HostMaintenanceError('Host still reports that a reboot is required.')


def postflight(state_file, *, project_root=PROJECT_ROOT):
    payload = read_state(state_file)
    before = payload['preflight']
    revision = run_live_checks(project_root)
    after = snapshot(revision)
    validate_postflight(before, after)
    completed = {
        'schema': 1,
        'phase': 'complete',
        'preflight': before,
        'postflight': after,
    }
    write_state(state_file, completed, replace=True)
    return completed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('preflight', 'postflight'))
    parser.add_argument('--state-file', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.phase == 'preflight':
            result = preflight(args.state_file)
            evidence = result['preflight']
            print(
                'Host maintenance preflight passed: '
                f'commit={evidence["repository_commit"][:12]} '
                f'boot={evidence["boot_id"]} '
                f'running_kernel={evidence["running_kernel"]} '
                f'expected_kernel={evidence["expected_kernel"]} '
                f'state={args.state_file}'
            )
        else:
            result = postflight(args.state_file)
            evidence = result['postflight']
            print(
                'Host maintenance postflight passed: '
                f'commit={evidence["repository_commit"][:12]} '
                f'boot={evidence["boot_id"]} '
                f'kernel={evidence["running_kernel"]} '
                f'state={args.state_file}'
            )
    except (HostMaintenanceError, OSError, ValueError) as error:
        parser.exit(1, f'Host maintenance {args.phase} failed: {error}\n')


if __name__ == '__main__':
    main()
