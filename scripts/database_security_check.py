#!/usr/bin/env python3
"""Verify live PostgreSQL role boundaries and record a private success marker."""

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import uuid


DEFAULT_STATUS_FILE = Path('/var/lib/pcep-db-security/last-success.json')
CONTAINER_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')


class DatabaseSecurityError(RuntimeError):
    pass


def load_deploy_backend():
    path = Path(__file__).with_name('deploy_backend.py')
    spec = importlib.util.spec_from_file_location('pcep_security_deploy_backend', path)
    if spec is None or spec.loader is None:
        raise DatabaseSecurityError('Cannot load the database role verifier.')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_container_name(value):
    if not CONTAINER_PATTERN.fullmatch(value):
        raise DatabaseSecurityError('Invalid database container name.')
    return value


def utc_moment(now=None):
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise DatabaseSecurityError('Current time must include a timezone.')
    return moment.astimezone(timezone.utc)


def write_success_status(path, now=None):
    status = Path(path).absolute()
    parent = status.parent
    if parent.is_symlink() or not parent.is_dir():
        raise DatabaseSecurityError(
            'Database security status directory must be a real directory.'
        )
    parent_details = parent.stat()
    if parent_details.st_uid != os.getuid() or parent_details.st_mode & 0o022:
        raise DatabaseSecurityError(
            'Database security status directory must be owned by the invoking '
            'user and not writable by group or others.'
        )
    if status.exists() or status.is_symlink():
        if status.is_symlink() or not status.is_file():
            raise DatabaseSecurityError(
                'Existing database security status must be a real file.'
            )
        if status.stat().st_uid != os.getuid():
            raise DatabaseSecurityError(
                'Existing database security status has the wrong owner.'
            )

    payload = {
        'completed_at': utc_moment(now).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'schema': 1,
    }
    temporary = parent / f'.{status.name}.partial-{uuid.uuid4().hex}'
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
        os.replace(temporary, status)
        status.chmod(0o600)
        directory = os.open(parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
    return payload


def execute(
    project_root,
    status_file=DEFAULT_STATUS_FILE,
    database_container='pcep_db',
    now=None,
    deploy_module=None,
):
    root = Path(project_root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise DatabaseSecurityError('Project root must be a real directory.')
    validate_container_name(database_container)
    deploy = deploy_module or load_deploy_backend()
    config = deploy.ReleaseConfig(
        project_root=root,
        backup_root=root,
        release='database-security-check',
        public_health_url='https://invalid.local/',
        database_container=database_container,
    )
    try:
        deploy.verify_database_roles(config)
    except deploy.ReleaseError as error:
        raise DatabaseSecurityError(str(error)) from error
    return write_success_status(status_file, now=now)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--project-root',
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument('--status-file', type=Path, default=DEFAULT_STATUS_FILE)
    parser.add_argument('--container', default='pcep_db')
    args = parser.parse_args()
    try:
        payload = execute(args.project_root, args.status_file, args.container)
    except (DatabaseSecurityError, OSError, ValueError) as error:
        parser.exit(1, f'Database security check failed: {error}\n')
    print(json.dumps(payload, separators=(',', ':'), sort_keys=True))


if __name__ == '__main__':
    main()
