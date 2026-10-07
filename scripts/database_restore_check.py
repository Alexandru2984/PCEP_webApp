#!/usr/bin/env python3
"""Restore the newest verified PCEP backup into an isolated PostgreSQL container."""

import argparse
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import time


DEFAULT_BACKUP_ROOT = Path('/home/micu/backups/pcep/daily')
DEFAULT_SOURCE_CONTAINER = 'pcep_db'
DEFAULT_RESTORE_CONTAINER = 'pcep_db_restore_check'
RESTORE_IMAGE_PROFILE = 'pcep-postgres-16-v1'
CONTAINER_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')
IMAGE_ID_PATTERN = re.compile(r'^sha256:[0-9a-f]{64}$')
IMAGE_REFERENCE_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._/:@-]{0,255}$')
POSTGRES_VERSION_PATTERN = re.compile(r'^postgres \(PostgreSQL\) (?P<major>\d+)(?:\.\d+)*$')

RESTORE_DATABASE = 'pcep_restore'
RESTORE_ADMIN = 'pcep_restore_admin'
RESTORE_APP_USER = 'pcep_user'
RESTORE_OWNER_ROLE = 'pcep_owner'
RESTORE_MIGRATOR_ROLE = 'pcep_migrator'
RESTORE_PASSWORD = 'disposable-restore-check-only'
ROLE_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,62}$')

VALIDATION_SQL = r"""
SELECT json_build_object(
    'questions', (SELECT count(*) FROM quiz_question),
    'choices', (SELECT count(*) FROM quiz_choice),
    'migrations', (SELECT count(*) FROM django_migrations),
    'question_owner', (
        SELECT pg_get_userbyid(relowner)
        FROM pg_class
        WHERE oid = 'public.quiz_question'::regclass
    ),
    'unique_index_valid', COALESCE((
        SELECT index.indisvalid
        FROM pg_index AS index
        JOIN pg_class AS relation ON relation.oid = index.indexrelid
        JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = 'public'
          AND relation.relname = 'one_correct_choice_per_question'
    ), false),
    'invalid_choice_counts', (
        SELECT count(*)
        FROM (
            SELECT question.id
            FROM quiz_question AS question
            LEFT JOIN quiz_choice AS choice ON choice.question_id = question.id
            GROUP BY question.id
            HAVING count(choice.id) <> 4
        ) AS invalid
    ),
    'invalid_correct_counts', (
        SELECT count(*)
        FROM (
            SELECT question.id
            FROM quiz_question AS question
            LEFT JOIN quiz_choice AS choice ON choice.question_id = question.id
            GROUP BY question.id
            HAVING count(choice.id) FILTER (WHERE choice.is_correct) <> 1
        ) AS invalid
    )
)::text;
"""


class RestoreCheckError(RuntimeError):
    pass


def load_database_backup():
    path = Path(__file__).with_name('database_backup.py')
    spec = importlib.util.spec_from_file_location('pcep_database_backup', path)
    if spec is None or spec.loader is None:
        raise RestoreCheckError('Cannot load the verified backup implementation.')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_container_name(value, label):
    if not CONTAINER_PATTERN.fullmatch(value):
        raise RestoreCheckError(f'Invalid {label} container name.')
    return value


def select_latest_backup(backup_root, backup_module=None):
    root = Path(backup_root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise RestoreCheckError('Backup root must be a real directory.')
    if root.stat().st_mode & 0o077:
        raise RestoreCheckError('Backup root must not be accessible by group or others.')

    backup_module = backup_module or load_database_backup()
    try:
        complete = backup_module.discover_complete_backups(root)
    except (OSError, backup_module.BackupError) as error:
        raise RestoreCheckError(f'Cannot verify daily backups: {error}') from error
    if not complete:
        raise RestoreCheckError('No complete verified daily backup is available.')
    return complete[0]


def run_command(command, *, timeout=30, input_text=None, check=True):
    try:
        result = subprocess.run(
            command,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as error:
        raise RestoreCheckError(f'Required executable is missing: {command[0]}') from error
    except subprocess.TimeoutExpired as error:
        raise RestoreCheckError(f'Command timed out: {command[0]}') from error
    if check and result.returncode:
        detail = result.stderr.strip()[-4000:] or result.stdout.strip()[-4000:]
        raise RestoreCheckError(
            f'Command failed ({result.returncode}): {command[0]}: {detail}'
        )
    return result


def source_image_id(source_container, runner=run_command):
    validate_container_name(source_container, 'source')
    result = runner(
        [
            'docker',
            'inspect',
            '--type',
            'container',
            '--format',
            '{{.Image}}',
            source_container,
        ]
    )
    image_id = result.stdout.strip()
    if not IMAGE_ID_PATTERN.fullmatch(image_id):
        raise RestoreCheckError('The source container returned an invalid image ID.')
    return image_id


def image_is_available(image_id, runner=run_command):
    if not IMAGE_ID_PATTERN.fullmatch(image_id):
        raise RestoreCheckError('Invalid source image ID.')
    result = runner(
        ['docker', 'image', 'inspect', image_id, '--format', '{{.Id}}'],
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == image_id


def source_postgres_major(source_container, runner=run_command):
    validate_container_name(source_container, 'source')
    result = runner(
        [
            'docker', 'exec', '--user', 'postgres', source_container,
            'postgres', '--version',
        ]
    )
    match = POSTGRES_VERSION_PATTERN.fullmatch(result.stdout.strip())
    if not match:
        raise RestoreCheckError('The source container returned an invalid PostgreSQL version.')
    return match.group('major')


def source_table_owner(source_container, runner=run_command):
    validate_container_name(source_container, 'source')
    result = runner(
        [
            'docker', 'exec', '--interactive', '--user', 'postgres', source_container,
            'sh', '-ceu',
            (
                'exec psql --no-psqlrc --no-password --tuples-only --no-align '
                '--quiet --set=ON_ERROR_STOP=on --username "$POSTGRES_USER" '
                '--dbname "$POSTGRES_DB"'
            ),
        ],
        input_text=(
            "SELECT pg_get_userbyid(relowner) FROM pg_class "
            "WHERE oid = 'public.quiz_question'::regclass;\n"
        ),
    )
    owner = result.stdout.strip()
    if owner not in {RESTORE_APP_USER, RESTORE_OWNER_ROLE}:
        raise RestoreCheckError(
            f'The source question table has an unexpected owner: {owner!r}.'
        )
    return owner


def validate_image_reference(value):
    if not value or not IMAGE_REFERENCE_PATTERN.fullmatch(value):
        raise RestoreCheckError('Fallback image must be a bounded local image reference.')
    return value


def verify_fallback_restore_image(reference, expected_major, runner=run_command):
    reference = validate_image_reference(reference)
    image_id = runner(
        ['docker', 'image', 'inspect', reference, '--format', '{{.Id}}']
    ).stdout.strip()
    if not IMAGE_ID_PATTERN.fullmatch(image_id):
        raise RestoreCheckError('The fallback image returned an invalid image ID.')

    raw_config = runner(
        ['docker', 'image', 'inspect', image_id, '--format', '{{json .Config}}']
    ).stdout
    try:
        config = json.loads(raw_config)
    except json.JSONDecodeError as error:
        raise RestoreCheckError('The fallback image has invalid metadata.') from error
    if not isinstance(config, dict):
        raise RestoreCheckError('The fallback image has invalid metadata.')
    if config.get('User') != 'postgres':
        raise RestoreCheckError('The fallback image must run as postgres.')
    if config.get('Entrypoint') != ['docker-entrypoint.sh'] or config.get('Cmd') != ['postgres']:
        raise RestoreCheckError('The fallback image has an unexpected entrypoint.')

    labels = config.get('Labels')
    environment = config.get('Env')
    if not isinstance(labels, dict) or not isinstance(environment, list):
        raise RestoreCheckError('The fallback image is missing required metadata.')
    if labels.get('com.pcep.restore-profile') != RESTORE_IMAGE_PROFILE:
        raise RestoreCheckError('The fallback image has the wrong restore profile.')

    environment_values = {}
    for entry in environment:
        if not isinstance(entry, str) or '=' not in entry:
            raise RestoreCheckError('The fallback image has invalid environment metadata.')
        name, value = entry.split('=', 1)
        environment_values[name] = value
    sensitive_names = sorted(
        name
        for name in environment_values
        if any(marker in name.upper() for marker in ('PASSWORD', 'SECRET', 'TOKEN'))
    )
    if sensitive_names:
        raise RestoreCheckError(
            'The fallback image embeds runtime secrets: ' + ', '.join(sensitive_names)
        )
    if environment_values.get('PG_MAJOR') != expected_major:
        raise RestoreCheckError('The fallback image PostgreSQL major version does not match.')
    return image_id


def select_restore_image(source_container, fallback_image=None, runner=run_command):
    live_image = source_image_id(source_container, runner)
    if image_is_available(live_image, runner):
        return live_image, False
    if not fallback_image:
        raise RestoreCheckError(
            'The exact live PostgreSQL image is unavailable. Supply only a reviewed '
            '--fallback-image or restore the exact image metadata.'
        )
    major = source_postgres_major(source_container, runner)
    fallback_id = verify_fallback_restore_image(fallback_image, major, runner)
    return fallback_id, True


def docker_run_command(container, image_id):
    validate_container_name(container, 'restore')
    if not IMAGE_ID_PATTERN.fullmatch(image_id):
        raise RestoreCheckError('Invalid restore image ID.')
    return [
        'docker',
        'run',
        '--detach',
        '--name',
        container,
        '--label',
        'com.pcep.restore-drill=true',
        '--network',
        'none',
        '--user',
        'postgres',
        '--read-only',
        '--cap-drop',
        'ALL',
        '--security-opt',
        'no-new-privileges:true',
        '--pids-limit',
        '128',
        '--memory',
        '768m',
        '--stop-timeout',
        '30',
        '--tmpfs',
        '/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777',
        '--tmpfs',
        '/var/run/postgresql:rw,noexec,nosuid,nodev,size=16m,mode=3775,uid=70,gid=70',
        '--tmpfs',
        '/var/lib/postgresql/data:rw,noexec,nosuid,nodev,size=256m,mode=0700,uid=70,gid=70',
        '--env',
        f'POSTGRES_DB={RESTORE_DATABASE}',
        '--env',
        f'POSTGRES_USER={RESTORE_ADMIN}',
        '--env',
        f'POSTGRES_PASSWORD={RESTORE_PASSWORD}',
        '--env',
        f'PCEP_APP_DB={RESTORE_DATABASE}',
        '--env',
        f'PCEP_APP_USER={RESTORE_APP_USER}',
        '--env',
        f'PCEP_APP_PASSWORD={RESTORE_PASSWORD}',
        '--env',
        f'PCEP_OWNER_ROLE={RESTORE_OWNER_ROLE}',
        '--env',
        f'PCEP_MIGRATOR_USER={RESTORE_MIGRATOR_ROLE}',
        image_id,
    ]


@contextmanager
def disposable_restore_container(container, image_id, runner=run_command):
    runner(docker_run_command(container, image_id), timeout=60)
    try:
        yield
    finally:
        runner(['docker', 'rm', '--force', container], timeout=60)


def container_logs(container):
    result = run_command(
        ['docker', 'logs', container], timeout=30, check=False
    )
    return (result.stderr or result.stdout).strip()[-4000:]


def wait_for_database(container, timeout_seconds=60):
    deadline = time.monotonic() + timeout_seconds
    command = [
        'docker',
        'exec',
        '--user',
        'postgres',
        container,
        'pg_isready',
        '--username',
        RESTORE_ADMIN,
        '--dbname',
        RESTORE_DATABASE,
    ]
    while time.monotonic() < deadline:
        if run_command(command, timeout=10, check=False).returncode == 0:
            return
        time.sleep(1)
    raise RestoreCheckError(
        f'Disposable PostgreSQL did not become ready: {container_logs(container)}'
    )


def verify_runtime_security(container):
    result = run_command(
        ['docker', 'exec', '--user', 'postgres', container, 'cat', '/proc/1/status']
    )
    if not re.search(r'^CapBnd:\s+0+$', result.stdout, re.MULTILINE):
        raise RestoreCheckError('Restore container retained Linux capabilities.')
    if not re.search(r'^NoNewPrivs:\s+1$', result.stdout, re.MULTILINE):
        raise RestoreCheckError('Restore container lacks no-new-privileges.')


def prepare_restore_roles(container):
    sql = f"""
DO $roles$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{RESTORE_OWNER_ROLE}') THEN
    CREATE ROLE {RESTORE_OWNER_ROLE}
      NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{RESTORE_MIGRATOR_ROLE}') THEN
    CREATE ROLE {RESTORE_MIGRATOR_ROLE}
      NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
  END IF;
END
$roles$;
"""
    run_command(
        [
            'docker', 'exec', '--interactive', '--user', 'postgres', container,
            'psql', '--username', RESTORE_ADMIN, '--dbname', RESTORE_DATABASE,
            '--no-password', '--no-psqlrc', '--set', 'ON_ERROR_STOP=on',
        ],
        input_text=sql,
    )


def restore_dump(backup, container, timeout_seconds=600):
    gzip_process = None
    restore_process = None
    try:
        gzip_process = subprocess.Popen(
            ['gzip', '--decompress', '--stdout', '--', str(backup)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        restore_process = subprocess.Popen(
            [
                'docker',
                'exec',
                '--interactive',
                '--user',
                'postgres',
                container,
                'psql',
                '--username',
                RESTORE_ADMIN,
                '--dbname',
                RESTORE_DATABASE,
                '--no-password',
                '--no-psqlrc',
                '--set',
                'ON_ERROR_STOP=on',
                '--single-transaction',
            ],
            stdin=gzip_process.stdout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as error:
        if gzip_process is not None:
            gzip_process.kill()
            gzip_process.wait()
        raise RestoreCheckError(f'Required executable is missing: {error.filename}') from error

    assert gzip_process.stdout is not None
    gzip_process.stdout.close()
    try:
        _, restore_stderr = restore_process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        restore_process.kill()
        gzip_process.kill()
        restore_process.communicate()
        gzip_process.wait()
        raise RestoreCheckError('Database restore timed out.') from error

    assert gzip_process.stderr is not None
    gzip_stderr = gzip_process.stderr.read()
    try:
        gzip_status = gzip_process.wait(timeout=30)
    except subprocess.TimeoutExpired as error:
        gzip_process.kill()
        gzip_process.wait()
        raise RestoreCheckError('Backup decompression did not terminate.') from error

    if restore_process.returncode or gzip_status:
        restore_detail = restore_stderr.decode(errors='replace').strip()[-4000:]
        gzip_detail = gzip_stderr.decode(errors='replace').strip()[-4000:]
        raise RestoreCheckError(
            'Database restore failed: '
            f'psql={restore_process.returncode}, gzip={gzip_status}: '
            f'{restore_detail or gzip_detail}'
        )


def validate_metrics(payload, expected_owner=RESTORE_APP_USER):
    if not ROLE_PATTERN.fullmatch(expected_owner):
        raise RestoreCheckError('Expected table owner is invalid.')
    try:
        metrics = json.loads(payload)
    except json.JSONDecodeError as error:
        raise RestoreCheckError('Restore validation returned invalid JSON.') from error
    if not isinstance(metrics, dict):
        raise RestoreCheckError('Restore validation did not return an object.')

    for key in ('questions', 'choices', 'migrations'):
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise RestoreCheckError(f'Restore validation failed for {key}.')
    if metrics.get('question_owner') != expected_owner:
        raise RestoreCheckError('Restored question table has the wrong owner.')
    if metrics.get('unique_index_valid') is not True:
        raise RestoreCheckError('The one-correct-choice index is absent or invalid.')
    for key in ('invalid_choice_counts', 'invalid_correct_counts'):
        if metrics.get(key) != 0:
            raise RestoreCheckError(f'Restored question integrity failed for {key}.')
    return metrics


def validate_restored_database(container, expected_owner=RESTORE_APP_USER):
    result = run_command(
        [
            'docker',
            'exec',
            '--user',
            'postgres',
            container,
            'psql',
            '--username',
            RESTORE_ADMIN,
            '--dbname',
            RESTORE_DATABASE,
            '--no-password',
            '--no-psqlrc',
            '--tuples-only',
            '--no-align',
            '--quiet',
            '--set',
            'ON_ERROR_STOP=on',
            '--command',
            VALIDATION_SQL,
        ],
        timeout=60,
    )
    return validate_metrics(result.stdout.strip(), expected_owner)


def validate_backup_in_isolation(backup, container, image_id, expected_owner):
    with disposable_restore_container(container, image_id):
        wait_for_database(container)
        verify_runtime_security(container)
        prepare_restore_roles(container)
        restore_dump(backup, container)
        return validate_restored_database(container, expected_owner)


def execute(backup_root, source_container, restore_container, fallback_image=None):
    validate_container_name(source_container, 'source')
    validate_container_name(restore_container, 'restore')
    backup_module = load_database_backup()
    backup, checksum = select_latest_backup(backup_root, backup_module)
    expected_owner = source_table_owner(source_container)
    image_id, used_fallback = select_restore_image(source_container, fallback_image)
    if used_fallback:
        print(
            'Exact live PostgreSQL image metadata is unavailable; using verified '
            f'fallback {fallback_image} ({image_id}).',
            flush=True,
        )

    metrics = validate_backup_in_isolation(
        backup, restore_container, image_id, expected_owner
    )

    backup_module.verify_checksum(backup, checksum)
    print(f'Isolated database restore passed: {backup}')
    print(f'PostgreSQL image ID: {image_id}')
    print(
        'Restored '
        f"{metrics['questions']} questions, {metrics['choices']} choices and "
        f"{metrics['migrations']} migrations."
    )
    return backup, image_id, metrics


def interrupted(signum, _frame):
    raise RestoreCheckError(f'Restore check interrupted by signal {signum}.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-root', type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument('--source-container', default=DEFAULT_SOURCE_CONTAINER)
    parser.add_argument('--restore-container', default=DEFAULT_RESTORE_CONTAINER)
    parser.add_argument(
        '--fallback-image',
        help=(
            'Reviewed local image used only when the exact live image metadata is '
            'unavailable; its runtime metadata and PostgreSQL major version are checked.'
        ),
    )
    args = parser.parse_args()
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        execute(
            args.backup_root,
            args.source_container,
            args.restore_container,
            args.fallback_image,
        )
    except (RestoreCheckError, OSError, ValueError) as error:
        parser.exit(1, f'Database restore check failed: {error}\n')


if __name__ == '__main__':
    main()
