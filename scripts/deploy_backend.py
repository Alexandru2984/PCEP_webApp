#!/usr/bin/env python3
"""Build and deploy the backend with a verified rollback image and database dump."""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.request import Request, urlopen
import uuid


RELEASE_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
IMAGE_ID_PATTERN = re.compile(r'sha256:[0-9a-f]{64}')
IMAGE_REFERENCE_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._/:@-]{0,255}')
BACKEND_IMAGE = 'pcep_webapp-backend:latest'
SENSITIVE_IMAGE_ENV_PREFIXES = (
    'CORS_',
    'DATABASE_',
    'DJANGO_',
    'PCEP_APP_',
    'POSTGRES_',
)
SENSITIVE_IMAGE_ENV_NAMES = {'ACCESS_TOKEN', 'PASSWORD', 'SECRET_KEY'}


class ReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseConfig:
    project_root: Path
    backup_root: Path
    release: str
    public_health_url: str
    health_timeout: int = 60
    backend_container: str = 'pcep_backend'
    database_container: str = 'pcep_db'
    allow_migrations: bool = False
    fallback_rollback_image: str | None = None


@dataclass(frozen=True)
class ReleaseResult:
    rollback_tag: str
    backup_path: Path
    backup_sha256: str


def run_command(args, *, cwd, env=None):
    subprocess.run(args, cwd=cwd, env=env, check=True)


def capture_command(args, *, cwd, env=None):
    completed = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()[-2000:]
        raise ReleaseError(
            f'Command failed with exit code {completed.returncode}: {detail or args[0]}'
        )
    return completed.stdout.strip()


def validate_release(value):
    if not RELEASE_PATTERN.fullmatch(value):
        raise ReleaseError('Release must contain 1-64 safe label characters.')
    return value


def validate_image_reference(value):
    if not IMAGE_REFERENCE_PATTERN.fullmatch(value):
        raise ReleaseError('Fallback rollback image must be a bounded local image reference.')
    return value


def git_release(project_root):
    release = capture_command(
        [
            'git', 'describe', '--always', '--dirty', '--abbrev=12',
            '--match', '__pcep_no_matching_tag__',
        ],
        cwd=project_root,
    )
    if release.endswith('-dirty'):
        raise ReleaseError('Refusing to deploy with tracked uncommitted changes.')
    return validate_release(release)


def release_environment(config):
    environment = os.environ.copy()
    environment['PCEP_RELEASE'] = config.release
    return environment


def ensure_tracked_tree_is_clean(project_root):
    status = capture_command(
        ['git', 'status', '--porcelain', '--untracked-files=no'],
        cwd=project_root,
    )
    if status:
        raise ReleaseError('Refusing to deploy with tracked uncommitted changes.')


def verify_fallback_rollback_image(config, image_reference):
    root = config.project_root
    image_id = capture_command(
        ['docker', 'image', 'inspect', image_reference, '--format', '{{.Id}}'],
        cwd=root,
    )
    if not IMAGE_ID_PATTERN.fullmatch(image_id):
        raise ReleaseError('The fallback rollback image has an invalid image ID.')

    raw_config = capture_command(
        ['docker', 'image', 'inspect', image_reference, '--format', '{{json .Config}}'],
        cwd=root,
    )
    try:
        image_config = json.loads(raw_config)
    except json.JSONDecodeError as error:
        raise ReleaseError('The fallback rollback image has invalid metadata.') from error
    if not isinstance(image_config, dict) or image_config.get('User') != 'appuser':
        raise ReleaseError('The fallback rollback image must run as appuser.')

    environment = image_config.get('Env')
    labels = image_config.get('Labels')
    if not isinstance(environment, list) or not isinstance(labels, dict):
        raise ReleaseError('The fallback rollback image is missing required metadata.')
    environment_values = {}
    for entry in environment:
        if not isinstance(entry, str) or '=' not in entry:
            raise ReleaseError('The fallback rollback image has invalid environment metadata.')
        name, value = entry.split('=', 1)
        environment_values[name] = value

    sensitive_names = sorted(
        name
        for name in environment_values
        if name in SENSITIVE_IMAGE_ENV_NAMES
        or name.startswith(SENSITIVE_IMAGE_ENV_PREFIXES)
    )
    if sensitive_names:
        raise ReleaseError(
            'The fallback rollback image embeds runtime secret keys: '
            + ', '.join(sensitive_names)
        )

    fallback_release = environment_values.get('PCEP_RELEASE', '')
    label_release = labels.get('org.opencontainers.image.revision', '')
    if (
        not RELEASE_PATTERN.fullmatch(fallback_release)
        or label_release != fallback_release
    ):
        raise ReleaseError(
            'The fallback rollback image must have matching safe release metadata.'
        )

    run_command(
        ['make', 'audit-image', f'BACKEND_IMAGE={image_id}'],
        cwd=root,
        env=release_environment(config),
    )
    run_command(
        [
            'docker', 'run', '--rm', '--network', 'none', '--read-only',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--pids-limit', '64', '--memory', '256m',
            '--tmpfs', '/tmp:size=16m,noexec,nosuid,nodev',
            '--entrypoint', 'python', image_id,
            '-m', 'pip', 'check',
        ],
        cwd=root,
    )
    return image_id, fallback_release


def snapshot_running_backend(config, stamp):
    root = config.project_root
    state = capture_command(
        [
            'docker', 'inspect', config.backend_container,
            '--format', (
                '{{.State.Running}} '
                '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} '
                '{{.Image}}'
            ),
        ],
        cwd=root,
    ).split()
    if len(state) != 3 or state[0] != 'true' or state[1] not in ('healthy', 'none'):
        raise ReleaseError('The current backend must be running and healthy before deployment.')

    running_image = state[2]
    current_release = capture_command(
        [
            'docker', 'inspect', config.backend_container,
            '--format', (
                '{{range .Config.Env}}{{if eq (index (split . "=") 0) '
                '"PCEP_RELEASE"}}{{index (split . "=") 1}}{{end}}{{end}}'
            ),
        ],
        cwd=root,
    ) or 'unknown'
    if not RELEASE_PATTERN.fullmatch(current_release):
        current_release = 'unknown'

    rollback_source = running_image
    rollback_release = current_release
    try:
        available_image = capture_command(
            ['docker', 'image', 'inspect', running_image, '--format', '{{.Id}}'],
            cwd=root,
        )
    except ReleaseError as error:
        if not config.fallback_rollback_image:
            raise ReleaseError(
                'The exact live image metadata is unavailable. Supply only a reviewed '
                '--fallback-rollback-image or restore the exact image before deployment.'
            ) from error
        rollback_source, rollback_release = verify_fallback_rollback_image(
            config,
            validate_image_reference(config.fallback_rollback_image),
        )
        print(
            'Exact live image metadata is unavailable; using verified fallback '
            f'{config.fallback_rollback_image} ({rollback_release}).',
            flush=True,
        )
    else:
        if available_image != running_image:
            raise ReleaseError('The local image does not match the running backend image.')

    rollback_tag = f'pcep-backend-rollback:{stamp}-release-{rollback_release}'
    run_command(['docker', 'tag', rollback_source, rollback_tag], cwd=root)
    tagged_image = capture_command(
        ['docker', 'image', 'inspect', rollback_tag, '--format', '{{.Id}}'],
        cwd=root,
    )
    if tagged_image != rollback_source:
        raise ReleaseError('The rollback tag does not match its verified source image.')
    return rollback_tag


def backup_database(config, stamp):
    backup_root = config.backup_root.absolute()
    if backup_root.is_symlink():
        raise ReleaseError('Backup root must not be a symlink.')
    backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup_root.chmod(0o700)

    final_path = backup_root / f'pcep_db_{stamp}.sql.gz'
    if final_path.exists():
        raise ReleaseError(f'Backup already exists: {final_path}')
    partial_path = backup_root / f'.{final_path.name}.partial-{uuid.uuid4().hex}'
    error_path = backup_root / f'.{final_path.name}.stderr-{uuid.uuid4().hex}'
    process = None
    try:
        descriptor = os.open(partial_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        error_descriptor = os.open(
            error_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(descriptor, 'wb') as raw_output, gzip.GzipFile(
            filename='', mode='wb', fileobj=raw_output, mtime=0
        ) as compressed, os.fdopen(error_descriptor, 'wb') as errors:
            process = subprocess.Popen(
                [
                    'docker', 'exec', config.database_container, 'sh', '-c',
                    'exec pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"',
                ],
                cwd=config.project_root,
                stdout=subprocess.PIPE,
                stderr=errors,
            )
            shutil.copyfileobj(process.stdout, compressed, length=1024 * 1024)
            process.stdout.close()
            return_code = process.wait()
        if return_code:
            message = error_path.read_text(errors='replace')[-2000:].strip()
            raise ReleaseError(f'pg_dump failed ({return_code}): {message}')

        with gzip.open(partial_path, 'rb') as backup:
            prefix = backup.read(512)
            if b'PostgreSQL database dump' not in prefix:
                raise ReleaseError('The database backup does not contain a pg_dump header.')
            while backup.read(1024 * 1024):
                pass
        os.replace(partial_path, final_path)
        final_path.chmod(0o600)
        digest_builder = hashlib.sha256()
        with final_path.open('rb') as backup:
            while chunk := backup.read(1024 * 1024):
                digest_builder.update(chunk)
        digest = digest_builder.hexdigest()
        return final_path, digest
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        partial_path.unlink(missing_ok=True)
        error_path.unlink(missing_ok=True)


def wait_for_backend(config):
    deadline = time.monotonic() + config.health_timeout
    while time.monotonic() < deadline:
        state = capture_command(
            [
                'docker', 'inspect', config.backend_container,
                '--format', (
                    '{{.State.Status}} '
                    '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}'
                ),
            ],
            cwd=config.project_root,
        ).split()
        if state == ['running', 'healthy']:
            return
        failed = (
            bool(state) and state[0] in ('dead', 'exited')
        ) or (
            len(state) > 1 and state[1] == 'unhealthy'
        )
        if failed:
            raise ReleaseError(f'Backend failed during startup: {" ".join(state)}')
        time.sleep(2)
    raise ReleaseError('Backend did not become healthy before the deployment timeout.')


def verify_public_release(config):
    request = Request(
        config.public_health_url,
        headers={'Accept-Encoding': 'identity', 'User-Agent': 'pcep-release-check/1'},
    )
    with urlopen(request, timeout=15) as response:
        try:
            payload = json.loads(response.read())
        except json.JSONDecodeError as error:
            raise ReleaseError('Public readiness did not return valid JSON.') from error
        public_release = response.headers.get('X-PCEP-Release')
    if payload != {'status': 'ok', 'database': 'up'}:
        raise ReleaseError('Public readiness returned an unexpected response.')
    if public_release != config.release:
        raise ReleaseError(
            f'Public release mismatch: expected {config.release}, received {public_release!r}.'
        )


def deploy(config):
    root = config.project_root
    environment = release_environment(config)
    ensure_tracked_tree_is_clean(root)
    run_command(['docker', 'compose', 'config', '--quiet'], cwd=root, env=environment)

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    rollback_tag = snapshot_running_backend(config, stamp)
    backup_path, backup_sha256 = backup_database(config, stamp)
    print(f'Rollback image retained: {rollback_tag}', flush=True)
    print(f'Verified database backup: {backup_path} ({backup_sha256})', flush=True)

    run_command(['docker', 'compose', 'build', 'backend'], cwd=root, env=environment)
    candidate_image = capture_command(
        ['docker', 'image', 'inspect', BACKEND_IMAGE, '--format', '{{.Id}}'],
        cwd=root,
        env=environment,
    )
    if not IMAGE_ID_PATTERN.fullmatch(candidate_image):
        raise ReleaseError('The candidate backend image has an invalid image ID.')
    candidate_release = capture_command(
        [
            'docker', 'compose', 'run', '--rm', '--no-deps', '--entrypoint', 'python',
            'backend', '-c', (
                'import os; '
                'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pcep_project.settings"); '
                'from django.conf import settings; print(settings.PCEP_RELEASE)'
            ),
        ],
        cwd=root,
        env=environment,
    )
    if candidate_release != config.release:
        raise ReleaseError(
            'Candidate release mismatch: '
            f'expected {config.release}, received {candidate_release!r}.'
        )
    run_command(
        [
            'docker', 'compose', 'run', '--rm', '--no-deps', '--entrypoint', 'python',
            'backend', 'manage.py', 'check', '--deploy', '--fail-level', 'WARNING',
        ],
        cwd=root,
        env=environment,
    )
    migration_command = 'showmigrations' if config.allow_migrations else 'migrate'
    migration_args = ['--plan'] if config.allow_migrations else ['--check']
    run_command(
        [
            'docker', 'compose', 'run', '--rm', '--no-deps', '--entrypoint', 'python',
            'backend', 'manage.py', migration_command, *migration_args,
        ],
        cwd=root,
        env=environment,
    )
    # Scan the exact image Compose just built while the verified live container
    # is still untouched. A scanner or vulnerability failure aborts safely here.
    run_command(
        ['make', 'audit-image', f'BACKEND_IMAGE={candidate_image}'],
        cwd=root,
        env=environment,
    )

    run_command(
        ['docker', 'compose', 'up', '-d', '--no-deps', 'backend'],
        cwd=root,
        env=environment,
    )
    wait_for_backend(config)
    run_command(
        [
            'docker', 'compose', 'exec', '-T', 'backend', 'python', 'manage.py',
            'check', '--deploy', '--fail-level', 'WARNING',
        ],
        cwd=root,
        env=environment,
    )
    run_command(
        [
            'docker', 'compose', 'exec', '-T', 'backend', 'python', 'manage.py',
            'migrate', '--check',
        ],
        cwd=root,
        env=environment,
    )
    run_command(
        [
            'docker', 'compose', 'exec', '-T', 'backend', 'python', 'manage.py',
            'audit_questions', '--database', '--fail-on-warnings',
        ],
        cwd=root,
        env=environment,
    )
    verify_public_release(config)
    return ReleaseResult(rollback_tag, backup_path, backup_sha256)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--backup-root', type=Path, default=Path('/home/micu/backups/pcep'))
    parser.add_argument('--release')
    parser.add_argument(
        '--public-health-url', default='https://pcep.micutu.com/api/health/'
    )
    parser.add_argument('--health-timeout', type=int, default=60)
    parser.add_argument(
        '--allow-migrations', action='store_true',
        help='Show and allow reviewed pending migrations; otherwise refuse them.',
    )
    parser.add_argument(
        '--fallback-rollback-image',
        help=(
            'Reviewed local image to retain only when exact live image metadata '
            'is unavailable; metadata, secrets, packages and vulnerabilities are checked.'
        ),
    )
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    release = validate_release(args.release) if args.release else git_release(project_root)
    if not 10 <= args.health_timeout <= 300:
        parser.error('--health-timeout must be between 10 and 300 seconds')
    config = ReleaseConfig(
        project_root=project_root,
        backup_root=args.backup_root,
        release=release,
        public_health_url=args.public_health_url,
        health_timeout=args.health_timeout,
        allow_migrations=args.allow_migrations,
        fallback_rollback_image=args.fallback_rollback_image,
    )
    try:
        result = deploy(config)
    except (OSError, ReleaseError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Backend deployment failed: {error}\n')
    print(f'Deployed backend release {release}')
    print(f'Rollback image: {result.rollback_tag}')
    print(f'Database backup: {result.backup_path}')
    print(f'Database backup SHA-256: {result.backup_sha256}')


if __name__ == '__main__':
    main()
