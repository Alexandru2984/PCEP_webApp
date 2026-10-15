#!/usr/bin/env python3
"""Verify that installed PCEP systemd policy exactly matches the repository."""

import argparse
import hashlib
from pathlib import Path
import re
import stat
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SYSTEMD_ROOT = Path('/etc/systemd/system')
SEO_GENERATOR = Path('/usr/local/sbin/pcep-seo-pages')
REQUIRED_UNITS = frozenset({
    'pcep-analytics-retention.service',
    'pcep-analytics-retention.timer',
    'pcep-database-security.service',
    'pcep-database-security.timer',
    'pcep-db-backup.service',
    'pcep-db-backup.timer',
    'pcep-db-restore-check.service',
    'pcep-db-restore-check.timer',
    'pcep-operations-health.service',
    'pcep-operations-health.timer',
    'pcep-seo-pages.service',
    'pcep-seo-pages.timer',
})
OPTIONAL_OFFSITE_UNITS = frozenset({
    'pcep-db-offsite.service',
    'pcep-db-backup.service.d/20-offsite.conf',
})
UNIT_PATTERN = re.compile(r'^pcep-[a-z0-9-]+\.(?:service|timer)$')
DROPIN_DIRECTORY_PATTERN = re.compile(r'^pcep-[a-z0-9-]+\.service\.d$')
DROPIN_PATTERN = re.compile(r'^[0-9][0-9]-[a-z0-9-]+\.conf$')


class OperationsInstallationError(RuntimeError):
    pass


def sha256(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def require_regular_file(path, label, expected_uid=None, expected_gid=None, mode=None):
    if path.is_symlink() or not path.is_file():
        raise OperationsInstallationError(f'{label} must be a regular file: {path}')
    details = path.stat()
    if mode is not None and stat.S_IMODE(details.st_mode) != mode:
        raise OperationsInstallationError(
            f'{label} must have mode {mode:04o}: {path}'
        )
    if (
        expected_uid is not None
        and expected_gid is not None
        and (details.st_uid, details.st_gid) != (expected_uid, expected_gid)
    ):
        raise OperationsInstallationError(f'{label} has unexpected ownership: {path}')


def require_safe_directory(path, label, expected_uid, expected_gid):
    if path.is_symlink() or not path.is_dir():
        raise OperationsInstallationError(f'{label} must be a real directory: {path}')
    details = path.stat()
    if (details.st_uid, details.st_gid) != (expected_uid, expected_gid):
        raise OperationsInstallationError(
            f'{label} has unexpected ownership: {path}'
        )
    if stat.S_IMODE(details.st_mode) & 0o022:
        raise OperationsInstallationError(
            f'{label} must not be writable by group or others: {path}'
        )


def unit_inventory(root):
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise OperationsInstallationError(
            f'Systemd root must be a real directory: {root}'
        )
    files = set()
    directories = set()
    for entry in root.iterdir():
        name = entry.name
        if UNIT_PATTERN.fullmatch(name):
            if entry.is_symlink() or not entry.is_file():
                raise OperationsInstallationError(
                    f'Unit must be a regular file: {entry}'
                )
            files.add(name)
        elif DROPIN_DIRECTORY_PATTERN.fullmatch(name):
            if entry.is_symlink() or not entry.is_dir():
                raise OperationsInstallationError(
                    f'Drop-in path must be a real directory: {entry}'
                )
            directories.add(name)
            for child in entry.iterdir():
                if (
                    child.is_symlink()
                    or not child.is_file()
                    or DROPIN_PATTERN.fullmatch(child.name) is None
                ):
                    raise OperationsInstallationError(
                        f'Unexpected PCEP drop-in entry: {child}'
                    )
                files.add(f'{name}/{child.name}')
        elif name.startswith('pcep-'):
            raise OperationsInstallationError(
                f'Unexpected PCEP systemd entry: {entry}'
            )
    return files, directories


def activation_inventory(root):
    entries = set()
    for directory in Path(root).iterdir():
        if not directory.name.endswith(('.wants', '.requires')):
            continue
        if not directory.is_dir():
            continue
        for child in directory.iterdir():
            if child.name.startswith('pcep-'):
                entries.add(f'{directory.name}/{child.name}')
    return entries


def timer_is_active(name):
    try:
        result = subprocess.run(
            ['/usr/bin/systemctl', 'is-active', '--quiet', name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise OperationsInstallationError(
            f'Cannot query the active state of {name}.'
        ) from error
    return result.returncode == 0


def service_is_failed(name):
    try:
        result = subprocess.run(
            ['/usr/bin/systemctl', 'is-failed', '--quiet', name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise OperationsInstallationError(
            f'Cannot query the failure state of {name}.'
        ) from error
    if result.returncode not in {0, 1}:
        raise OperationsInstallationError(
            f'Cannot query the failure state of {name}.'
        )
    return result.returncode == 0


def verify_installation(
    project_root=PROJECT_ROOT,
    systemd_root=SYSTEMD_ROOT,
    seo_generator=SEO_GENERATOR,
    expected_uid=0,
    expected_gid=0,
    active_timer_check=None,
    failed_service_check=None,
):
    project_root = Path(project_root).resolve()
    source_root = project_root / 'ops/systemd'
    systemd_root = Path(systemd_root).absolute()
    source_files, source_directories = unit_inventory(source_root)
    expected_files = REQUIRED_UNITS | OPTIONAL_OFFSITE_UNITS
    expected_directories = {
        path.split('/', 1)[0]
        for path in OPTIONAL_OFFSITE_UNITS
        if '/' in path
    }
    if source_files != expected_files or source_directories != expected_directories:
        raise OperationsInstallationError(
            'Repository systemd inventory is not the reviewed allowlist.'
        )

    require_safe_directory(
        systemd_root, 'Systemd root', expected_uid, expected_gid
    )
    installed_files, installed_directories = unit_inventory(systemd_root)
    missing = REQUIRED_UNITS - installed_files
    unexpected = installed_files - expected_files
    if missing:
        raise OperationsInstallationError(
            f'Required PCEP unit is missing: {sorted(missing)[0]}'
        )
    if unexpected:
        raise OperationsInstallationError(
            f'Unexpected PCEP unit is installed: {sorted(unexpected)[0]}'
        )
    optional_present = installed_files & OPTIONAL_OFFSITE_UNITS
    if optional_present and optional_present != OPTIONAL_OFFSITE_UNITS:
        raise OperationsInstallationError(
            'Offsite backup systemd policy is only partially installed.'
        )
    allowed_directories = expected_directories if optional_present else set()
    if installed_directories != allowed_directories:
        raise OperationsInstallationError(
            'Installed PCEP drop-in directories drifted from policy.'
        )
    for name in installed_directories:
        require_safe_directory(
            systemd_root / name,
            f'{name} installed drop-in directory',
            expected_uid,
            expected_gid,
        )

    for name in sorted(installed_files):
        source = source_root / name
        installed = systemd_root / name
        require_regular_file(source, f'{name} source')
        require_regular_file(
            installed,
            f'{name} installed unit',
            expected_uid,
            expected_gid,
            0o644,
        )
        if sha256(source) != sha256(installed):
            raise OperationsInstallationError(
                f'{name} installed hash does not match the repository.'
            )

    enabled_root = systemd_root / 'timers.target.wants'
    require_safe_directory(
        enabled_root,
        'Systemd timer enablement directory',
        expected_uid,
        expected_gid,
    )
    timers = sorted(name for name in REQUIRED_UNITS if name.endswith('.timer'))
    active_timer_check = active_timer_check or timer_is_active
    for name in timers:
        link = enabled_root / name
        if not link.is_symlink():
            raise OperationsInstallationError(f'{name} must be enabled by symlink.')
        details = link.lstat()
        if (details.st_uid, details.st_gid) != (expected_uid, expected_gid):
            raise OperationsInstallationError(
                f'{name} enablement symlink has unexpected ownership.'
            )
        try:
            target = link.resolve(strict=True)
        except OSError as error:
            raise OperationsInstallationError(
                f'{name} enablement symlink is broken.'
            ) from error
        if target != (systemd_root / name).resolve(strict=True):
            raise OperationsInstallationError(
                f'{name} enablement symlink targets the wrong unit.'
            )
        if not active_timer_check(name):
            raise OperationsInstallationError(f'{name} must be active.')

    # The publisher is executing inside its own service, so inspect the other
    # scheduled jobs only. A failed oneshot remains failed until a later
    # successful run and must not hide behind an active timer.
    failed_service_check = failed_service_check or service_is_failed
    monitored_services = {
        name
        for name in installed_files
        if name.endswith('.service')
        and name != 'pcep-operations-health.service'
    }
    for name in sorted(monitored_services):
        if failed_service_check(name):
            raise OperationsInstallationError(
                f'Scheduled PCEP service is failed: {name}'
            )

    expected_activations = {
        f'timers.target.wants/{name}' for name in timers
    }
    activations = activation_inventory(systemd_root)
    if activations != expected_activations:
        unexpected_activation = sorted(activations - expected_activations)
        if unexpected_activation:
            raise OperationsInstallationError(
                'Unexpected PCEP systemd activation is installed: '
                f'{unexpected_activation[0]}'
            )
        raise OperationsInstallationError(
            'Required PCEP timer activation is missing.'
        )

    seo_source = project_root / 'scripts/pcep-seo-pages.py'
    seo_generator = Path(seo_generator).absolute()
    require_regular_file(seo_source, 'SEO generator source')
    require_safe_directory(
        seo_generator.parent,
        'Installed SEO generator directory',
        expected_uid,
        expected_gid,
    )
    require_regular_file(
        seo_generator,
        'Installed SEO generator',
        expected_uid,
        expected_gid,
        0o755,
    )
    if sha256(seo_source) != sha256(seo_generator):
        raise OperationsInstallationError(
            'Installed SEO generator hash does not match the repository.'
        )

    return {
        'units': len(installed_files),
        'timers': len(timers),
        'offsite': optional_present == OPTIONAL_OFFSITE_UNITS,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=PROJECT_ROOT)
    parser.add_argument('--systemd-root', type=Path, default=SYSTEMD_ROOT)
    parser.add_argument('--seo-generator', type=Path, default=SEO_GENERATOR)
    parser.add_argument('--expected-uid', type=int, default=0)
    parser.add_argument('--expected-gid', type=int, default=0)
    args = parser.parse_args()
    try:
        result = verify_installation(
            args.project_root,
            args.systemd_root,
            args.seo_generator,
            args.expected_uid,
            args.expected_gid,
        )
    except (OSError, OperationsInstallationError, ValueError) as error:
        parser.exit(1, f'Operations installation verification failed: {error}\n')
    print(
        'Operations installation verified: '
        f'{result["units"]} units, {result["timers"]} enabled timers, '
        f'offsite={"installed" if result["offsite"] else "not-configured"}.'
    )


if __name__ == '__main__':
    main()
