#!/usr/bin/env python3
"""Verify that the active PCEP Nginx files exactly match the repository."""

import argparse
import hashlib
import os
from pathlib import Path
import stat


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VHOSTS = {
    'pcep.micutu.com': 'pcep.micutu.com.conf',
    'pcep-runner.micutu.com': 'pcep-runner.micutu.com.conf',
}
SNIPPETS = (
    'pcep-analytics-proxy.conf',
    'pcep-base-headers.conf',
    'pcep-csp.conf',
    'pcep-proxy.conf',
    'pcep-retired-content.conf',
    'pcep-runner-headers.conf',
)


def sha256(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def require_regular_file(path, label, expected_uid, expected_gid):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'{label} must be a regular file: {path}')
    details = path.stat()
    if stat.S_IMODE(details.st_mode) != 0o644:
        raise ValueError(f'{label} must have mode 0644: {path}')
    if (details.st_uid, details.st_gid) != (expected_uid, expected_gid):
        raise ValueError(f'{label} has unexpected ownership: {path}')


def require_source(path, label):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'{label} source must be a regular file: {path}')


def verify_installation(project_root, nginx_root, expected_uid=0, expected_gid=0):
    project_root = Path(project_root).resolve()
    nginx_root = Path(nginx_root).absolute()

    for live_name, source_name in VHOSTS.items():
        source = project_root / 'nginx' / source_name
        available = nginx_root / 'sites-available' / live_name
        enabled = nginx_root / 'sites-enabled' / live_name
        require_source(source, f'{live_name} vhost')
        require_regular_file(available, f'{live_name} available vhost', expected_uid, expected_gid)
        if sha256(source) != sha256(available):
            raise ValueError(f'{live_name} available vhost hash does not match the repository.')
        if not enabled.is_symlink():
            raise ValueError(f'{live_name} enabled vhost must be a symlink: {enabled}')
        enabled_details = enabled.lstat()
        if (enabled_details.st_uid, enabled_details.st_gid) != (expected_uid, expected_gid):
            raise ValueError(f'{live_name} enabled symlink has unexpected ownership: {enabled}')
        try:
            enabled_target = enabled.resolve(strict=True)
        except OSError as error:
            raise ValueError(f'{live_name} enabled symlink is broken: {enabled}') from error
        if enabled_target != available.resolve(strict=True):
            raise ValueError(f'{live_name} enabled symlink does not target sites-available.')

    for name in SNIPPETS:
        source = project_root / 'nginx' / 'snippets' / name
        installed = nginx_root / 'snippets' / name
        require_source(source, f'{name} snippet')
        require_regular_file(installed, f'{name} installed snippet', expected_uid, expected_gid)
        if sha256(source) != sha256(installed):
            raise ValueError(f'{name} installed snippet hash does not match the repository.')

    return {'vhosts': len(VHOSTS), 'snippets': len(SNIPPETS)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=PROJECT_ROOT)
    parser.add_argument('--nginx-root', type=Path, default=Path('/etc/nginx'))
    parser.add_argument('--expected-uid', type=int, default=0)
    parser.add_argument('--expected-gid', type=int, default=0)
    args = parser.parse_args()
    try:
        result = verify_installation(
            args.project_root,
            args.nginx_root,
            args.expected_uid,
            args.expected_gid,
        )
    except (OSError, ValueError) as error:
        parser.exit(1, f'Nginx installation verification failed: {error}\n')
    print(
        'Nginx installation verified: '
        f'{result["vhosts"]} active vhosts and {result["snippets"]} snippets match.'
    )


if __name__ == '__main__':
    main()
