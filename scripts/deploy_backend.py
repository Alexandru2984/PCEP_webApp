#!/usr/bin/env python3
"""Build and deploy the backend with a verified rollback image and database dump."""

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen
import uuid


def load_operation_lock():
    path = Path(__file__).with_name('operation_lock.py')
    spec = importlib.util.spec_from_file_location('pcep_operation_lock', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('Cannot load the operation-lock implementation.')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


operation_lock = load_operation_lock()
OperationLockError = operation_lock.OperationLockError
exclusive_operation_lock = operation_lock.exclusive_operation_lock


RELEASE_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
IMAGE_ID_PATTERN = re.compile(r'sha256:[0-9a-f]{64}')
IMAGE_REFERENCE_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._/:@-]{0,255}')
BACKEND_IMAGE = 'pcep_webapp-backend:latest'
APP_DATABASE_ROLE = 'pcep_user'
DATABASE_OWNER_ROLE = 'pcep_owner'
DATABASE_MIGRATOR_ROLE = 'pcep_migrator'
MAX_DATABASE_BACKUP_ERROR_BYTES = 64 * 1024
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
    lock_root: Path | None = None


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


def database_admin_sql(config, sql):
    """Run SQL over the container-local socket without exposing admin secrets."""
    command = [
        'docker', 'exec', '--interactive', '--user', 'postgres',
        config.database_container, 'sh', '-ceu',
        (
            'exec psql --no-psqlrc --no-password --set=ON_ERROR_STOP=on '
            '--tuples-only --no-align --quiet '
            '--username "$POSTGRES_USER" --dbname "$POSTGRES_DB"'
        ),
    ]
    completed = subprocess.run(
        command,
        cwd=config.project_root,
        input=sql,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()[-2000:]
        raise ReleaseError(
            'PostgreSQL administrator command failed '
            f'({completed.returncode}): {detail or "psql"}'
        )
    return completed.stdout.strip()


def verify_database_roles(config):
    payload = database_admin_sql(
        config,
        f"""
SELECT json_build_object(
  'app_role', (
    SELECT json_build_object(
      'login', rolcanlogin,
      'inherit', rolinherit,
      'superuser', rolsuper,
      'createdb', rolcreatedb,
      'createrole', rolcreaterole,
      'replication', rolreplication,
      'bypassrls', rolbypassrls
    ) FROM pg_roles WHERE rolname = '{APP_DATABASE_ROLE}'
  ),
  'owner_role', (
    SELECT json_build_object(
      'login', rolcanlogin,
      'inherit', rolinherit,
      'superuser', rolsuper,
      'createdb', rolcreatedb,
      'createrole', rolcreaterole,
      'replication', rolreplication,
      'bypassrls', rolbypassrls
    ) FROM pg_roles WHERE rolname = '{DATABASE_OWNER_ROLE}'
  ),
  'migrator_role', (
    SELECT json_build_object(
      'login', rolcanlogin,
      'inherit', rolinherit,
      'password_absent', rolpassword IS NULL,
      'superuser', rolsuper,
      'createdb', rolcreatedb,
      'createrole', rolcreaterole,
      'replication', rolreplication,
      'bypassrls', rolbypassrls
    ) FROM pg_authid WHERE rolname = '{DATABASE_MIGRATOR_ROLE}'
  ),
  'migrator_is_owner_member', pg_has_role(
    '{DATABASE_MIGRATOR_ROLE}', '{DATABASE_OWNER_ROLE}', 'MEMBER'
  ),
  'app_is_owner_member', pg_has_role(
    '{APP_DATABASE_ROLE}', '{DATABASE_OWNER_ROLE}', 'MEMBER'
  ),
  'unexpected_owner_members', (
    SELECT count(*) FROM pg_auth_members
    WHERE roleid = (SELECT oid FROM pg_roles WHERE rolname = '{DATABASE_OWNER_ROLE}')
      AND member <> (SELECT oid FROM pg_roles WHERE rolname = '{DATABASE_MIGRATOR_ROLE}')
  ),
  'unexpected_role_memberships', (
    SELECT count(*) FROM pg_auth_members
    WHERE member IN (
      SELECT oid FROM pg_roles
      WHERE rolname IN (
        '{APP_DATABASE_ROLE}', '{DATABASE_OWNER_ROLE}', '{DATABASE_MIGRATOR_ROLE}'
      )
    )
      AND NOT (
        roleid = (SELECT oid FROM pg_roles WHERE rolname = '{DATABASE_OWNER_ROLE}')
        AND member = (SELECT oid FROM pg_roles WHERE rolname = '{DATABASE_MIGRATOR_ROLE}')
      )
  ),
  'database_owner', (
    SELECT pg_get_userbyid(datdba) FROM pg_database
    WHERE datname = current_database()
  ),
  'schema_owner', (
    SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'public'
  ),
  'app_connect', has_database_privilege(
    '{APP_DATABASE_ROLE}', current_database(), 'CONNECT'
  ),
  'app_create_database_objects', has_database_privilege(
    '{APP_DATABASE_ROLE}', current_database(), 'CREATE'
  ),
  'app_temporary', has_database_privilege(
    '{APP_DATABASE_ROLE}', current_database(), 'TEMPORARY'
  ),
  'app_schema_usage', has_schema_privilege(
    '{APP_DATABASE_ROLE}', 'public', 'USAGE'
  ),
  'app_schema_create', has_schema_privilege(
    '{APP_DATABASE_ROLE}', 'public', 'CREATE'
  ),
  'wrong_table_owners', (
    SELECT count(*) FROM pg_class AS relation
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname = 'public'
      AND relation.relkind IN ('r', 'p', 'v', 'm', 'f')
      AND pg_get_userbyid(relation.relowner) <> '{DATABASE_OWNER_ROLE}'
  ),
  'wrong_sequence_owners', (
    SELECT count(*) FROM pg_class AS relation
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname = 'public'
      AND relation.relkind = 'S'
      AND pg_get_userbyid(relation.relowner) <> '{DATABASE_OWNER_ROLE}'
  ),
  'tables_without_app_dml', (
    SELECT count(*) FROM pg_class AS relation
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname = 'public'
      AND relation.relkind IN ('r', 'p', 'v', 'm', 'f')
      AND NOT (
        has_table_privilege('{APP_DATABASE_ROLE}', relation.oid, 'SELECT')
        AND has_table_privilege('{APP_DATABASE_ROLE}', relation.oid, 'INSERT')
        AND has_table_privilege('{APP_DATABASE_ROLE}', relation.oid, 'UPDATE')
        AND has_table_privilege('{APP_DATABASE_ROLE}', relation.oid, 'DELETE')
      )
  ),
  'tables_with_app_ddl', (
    SELECT count(*) FROM pg_class AS relation
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname = 'public'
      AND relation.relkind IN ('r', 'p', 'v', 'm', 'f')
      AND (
        has_table_privilege('{APP_DATABASE_ROLE}', relation.oid, 'TRUNCATE')
        OR has_table_privilege('{APP_DATABASE_ROLE}', relation.oid, 'REFERENCES')
        OR has_table_privilege('{APP_DATABASE_ROLE}', relation.oid, 'TRIGGER')
      )
  ),
  'sequences_without_app_runtime', (
    SELECT count(*) FROM pg_class AS relation
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname = 'public'
      AND CASE WHEN relation.relkind = 'S' THEN NOT (
          has_sequence_privilege('{APP_DATABASE_ROLE}', relation.oid, 'USAGE')
          AND has_sequence_privilege('{APP_DATABASE_ROLE}', relation.oid, 'SELECT')
        ) ELSE false END
  ),
  'sequences_with_app_update', (
    SELECT count(*) FROM pg_class AS relation
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname = 'public'
      AND CASE WHEN relation.relkind = 'S' THEN
        has_sequence_privilege('{APP_DATABASE_ROLE}', relation.oid, 'UPDATE')
      ELSE false END
  ),
  'default_table_app_privileges', (
    SELECT COALESCE(
      json_agg(privilege_type ORDER BY privilege_type), '[]'::json
    )
    FROM pg_default_acl AS defaults
    CROSS JOIN LATERAL aclexplode(defaults.defaclacl) AS privilege
    WHERE defaults.defaclrole = (
        SELECT oid FROM pg_roles WHERE rolname = '{DATABASE_OWNER_ROLE}'
      )
      AND defaults.defaclnamespace = (
        SELECT oid FROM pg_namespace WHERE nspname = 'public'
      )
      AND defaults.defaclobjtype = 'r'
      AND privilege.grantee = (
        SELECT oid FROM pg_roles WHERE rolname = '{APP_DATABASE_ROLE}'
      )
  ),
  'default_sequence_app_privileges', (
    SELECT COALESCE(
      json_agg(privilege_type ORDER BY privilege_type), '[]'::json
    )
    FROM pg_default_acl AS defaults
    CROSS JOIN LATERAL aclexplode(defaults.defaclacl) AS privilege
    WHERE defaults.defaclrole = (
        SELECT oid FROM pg_roles WHERE rolname = '{DATABASE_OWNER_ROLE}'
      )
      AND defaults.defaclnamespace = (
        SELECT oid FROM pg_namespace WHERE nspname = 'public'
      )
      AND defaults.defaclobjtype = 'S'
      AND privilege.grantee = (
        SELECT oid FROM pg_roles WHERE rolname = '{APP_DATABASE_ROLE}'
      )
  ),
  'unexpected_default_grants', (
    SELECT count(*)
    FROM pg_default_acl AS defaults
    CROSS JOIN LATERAL aclexplode(defaults.defaclacl) AS privilege
    WHERE defaults.defaclrole = (
        SELECT oid FROM pg_roles WHERE rolname = '{DATABASE_OWNER_ROLE}'
      )
      AND defaults.defaclnamespace = (
        SELECT oid FROM pg_namespace WHERE nspname = 'public'
      )
      AND (
        (
          defaults.defaclobjtype IN ('r', 'S')
          AND privilege.grantee NOT IN (
            defaults.defaclrole,
            (SELECT oid FROM pg_roles WHERE rolname = '{APP_DATABASE_ROLE}')
          )
        ) OR (
          defaults.defaclobjtype = 'f'
          AND privilege.grantee <> defaults.defaclrole
        )
      )
  )
)::text;
""",
    )
    try:
        posture = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ReleaseError('Database role verification returned invalid JSON.') from error

    expected_limited_role = {
        'login': False,
        'inherit': False,
        'superuser': False,
        'createdb': False,
        'createrole': False,
        'replication': False,
        'bypassrls': False,
    }
    expected = {
        'app_role': {**expected_limited_role, 'login': True, 'inherit': True},
        'owner_role': expected_limited_role,
        'migrator_role': {**expected_limited_role, 'password_absent': True},
        'migrator_is_owner_member': True,
        'app_is_owner_member': False,
        'unexpected_owner_members': 0,
        'unexpected_role_memberships': 0,
        'database_owner': DATABASE_OWNER_ROLE,
        'schema_owner': DATABASE_OWNER_ROLE,
        'app_connect': True,
        'app_create_database_objects': False,
        'app_temporary': False,
        'app_schema_usage': True,
        'app_schema_create': False,
        'wrong_table_owners': 0,
        'wrong_sequence_owners': 0,
        'tables_without_app_dml': 0,
        'tables_with_app_ddl': 0,
        'sequences_without_app_runtime': 0,
        'sequences_with_app_update': 0,
        'default_table_app_privileges': [
            'DELETE', 'INSERT', 'SELECT', 'UPDATE'
        ],
        'default_sequence_app_privileges': ['SELECT', 'USAGE'],
        'unexpected_default_grants': 0,
    }
    if posture != expected:
        raise ReleaseError(
            'Database roles are not in the reviewed least-privilege posture: '
            + json.dumps(posture, sort_keys=True)
        )
    return posture


def sql_literal(value):
    return "'" + value.replace("'", "''") + "'"


def run_reviewed_migrations(config, environment):
    password = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)
    database_admin_sql(
        config,
        f"""
BEGIN;
SELECT pg_advisory_xact_lock(hashtextextended('pcep-migrator-activation', 0));
DO $activate_migrator$
DECLARE
  currently_login boolean;
  password_present boolean;
BEGIN
  SELECT rolcanlogin, rolpassword IS NOT NULL
    INTO currently_login, password_present
    FROM pg_authid
    WHERE rolname = '{DATABASE_MIGRATOR_ROLE}';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'migration role is missing';
  END IF;
  IF currently_login OR password_present THEN
    RAISE EXCEPTION 'migration role is already active';
  END IF;
END
$activate_migrator$;
ALTER ROLE {DATABASE_MIGRATOR_ROLE}
  LOGIN PASSWORD {sql_literal(password)}
  VALID UNTIL {sql_literal(expires.isoformat())};
COMMIT;
""",
    )
    migration_environment = environment.copy()
    migration_environment.update(
        {
            'POSTGRES_USER': DATABASE_MIGRATOR_ROLE,
            'POSTGRES_PASSWORD': password,
            'PGOPTIONS': f'-c role={DATABASE_OWNER_ROLE}',
        }
    )
    command = [
        'docker', 'compose', '--profile', 'maintenance', 'run', '--rm',
        '--no-deps', '--env', 'POSTGRES_USER', '--env', 'POSTGRES_PASSWORD',
        '--env', 'PGOPTIONS', 'backend-migrate',
    ]
    try:
        run_command(command, cwd=config.project_root, env=migration_environment)
    finally:
        database_admin_sql(
            config,
            f'ALTER ROLE {DATABASE_MIGRATOR_ROLE} NOLOGIN PASSWORD NULL;\n',
        )
    verify_database_roles(config)


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


def fsync_directory(path):
    flags = (
        os.O_RDONLY
        | getattr(os, 'O_CLOEXEC', 0)
        | getattr(os, 'O_DIRECTORY', 0)
    )
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise ReleaseError('Backup root must remain a real directory.')
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def remove_backup_temporaries_durably(paths, parent):
    removed = False
    failures = []
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except BaseException as error:
            failures.append(error)
        else:
            removed = True
    if removed:
        try:
            fsync_directory(parent)
        except BaseException as error:
            failures.append(error)
    if failures:
        primary = failures[0]
        for failure in failures[1:]:
            primary.add_note(f'Additional backup cleanup failure: {failure}')
        raise primary
    return removed


def drain_bounded_stream_tail(stream, limit, state):
    tail = bytearray()
    try:
        while chunk := stream.read(64 * 1024):
            tail.extend(chunk)
            if len(tail) > limit:
                del tail[:-limit]
    except BaseException as error:
        state['error'] = error
    finally:
        try:
            stream.close()
        except BaseException as error:
            state.setdefault('error', error)
    state['tail'] = bytes(tail)


def bounded_process_diagnostic(value, limit=2000):
    decoded = value.decode(errors='replace')
    printable = ''.join(
        character if character.isprintable() else ' '
        for character in decoded
    )
    detail = ' '.join(printable.split()) or 'no diagnostic output'
    return detail[-limit:]


def backup_database(config, stamp, filename_prefix='pcep_db'):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,31}', filename_prefix):
        raise ReleaseError('Database backup prefix must be a bounded safe label.')
    if not re.fullmatch(r'\d{8}T\d{6}Z', stamp):
        raise ReleaseError('Database backup timestamp must be a UTC basic timestamp.')
    backup_root = config.backup_root.absolute()
    if backup_root.is_symlink():
        raise ReleaseError('Backup root must not be a symlink.')
    backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup_root.chmod(0o700)

    final_path = backup_root / f'{filename_prefix}_{stamp}.sql.gz'
    if final_path.exists():
        raise ReleaseError(f'Backup already exists: {final_path}')
    partial_path = backup_root / f'.{final_path.name}.partial-{uuid.uuid4().hex}'
    process = None
    stderr_thread = None
    stderr_state = {}
    primary_error = None
    try:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, 'O_CLOEXEC', 0)
        )
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(partial_path, flags, 0o600)
        with os.fdopen(descriptor, 'wb') as raw_output, gzip.GzipFile(
            filename='', mode='wb', fileobj=raw_output, mtime=0
        ) as compressed:
            process = subprocess.Popen(
                [
                    'docker', 'exec', config.database_container, 'sh', '-c',
                    'exec pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"',
                ],
                cwd=config.project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if process.stdout is None or process.stderr is None:
                raise ReleaseError('pg_dump output pipes were not created.')
            stderr_thread = threading.Thread(
                target=drain_bounded_stream_tail,
                args=(
                    process.stderr,
                    MAX_DATABASE_BACKUP_ERROR_BYTES,
                    stderr_state,
                ),
                name='pcep-pg-dump-stderr',
                daemon=True,
            )
            stderr_thread.start()
            shutil.copyfileobj(process.stdout, compressed, length=1024 * 1024)
            process.stdout.close()
            return_code = process.wait()
            stderr_thread.join(timeout=5)
            if stderr_thread.is_alive():
                raise ReleaseError('Timed out draining bounded pg_dump stderr.')
            if 'error' in stderr_state:
                raise ReleaseError(
                    f'Failed to read bounded pg_dump stderr: '
                    f'{stderr_state["error"]}'
                )
        if return_code:
            message = bounded_process_diagnostic(
                stderr_state.get('tail', b'')
            )
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
            os.fsync(backup.fileno())
        fsync_directory(backup_root)
        digest = digest_builder.hexdigest()
        return final_path, digest
    except BaseException as error:
        primary_error = error
        raise
    finally:
        cleanup_failures = []
        try:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            if stderr_thread is not None and stderr_thread.is_alive():
                stderr_thread.join(timeout=5)
                if stderr_thread.is_alive():
                    raise ReleaseError(
                        'Timed out cleaning up the bounded pg_dump stderr reader.'
                    )
        except BaseException as error:
            cleanup_failures.append(error)
        try:
            remove_backup_temporaries_durably(
                (partial_path,),
                backup_root,
            )
        except BaseException as error:
            cleanup_failures.append(error)
        if cleanup_failures:
            if primary_error is None:
                cleanup_error = cleanup_failures[0]
                for failure in cleanup_failures[1:]:
                    cleanup_error.add_note(
                        f'Additional database backup cleanup failure: {failure}'
                    )
                raise cleanup_error
            for cleanup_error in cleanup_failures:
                note = f'Database backup cleanup also failed: {cleanup_error}'
                primary_error.add_note(note)
                try:
                    print(
                        f'Backend deploy cleanup warning: {note}',
                        file=sys.stderr,
                    )
                except BaseException as warning_error:
                    primary_error.add_note(
                        f'Failed to emit backup cleanup warning: {warning_error}'
                    )


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


def verify_backend_runtime(config, expected_image):
    """Fail closed when Compose weakens the live backend isolation contract."""
    payload = capture_command(
        ['docker', 'inspect', config.backend_container],
        cwd=config.project_root,
    )
    try:
        containers = json.loads(payload)
        if not isinstance(containers, list) or len(containers) != 1:
            raise ValueError
        container = containers[0]
        host = container['HostConfig']
        runtime = container['Config']
        environment = runtime['Env']
        if not isinstance(environment, list) or not all(
            isinstance(entry, str) for entry in environment
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ReleaseError('Backend runtime inspection returned invalid JSON.') from error

    def exact_environment(name, value):
        return environment.count(f'{name}={value}') == 1 and sum(
            entry.startswith(f'{name}=') for entry in environment
        ) == 1

    posture = {
        'expected_image': container.get('Image') == expected_image,
        'unprivileged_user': runtime.get('User') == 'appuser',
        'production_mode_pinned': exact_environment('DJANGO_PRODUCTION', 'True'),
        'debug_disabled': exact_environment('DJANGO_DEBUG', 'False'),
        'read_only_root': host.get('ReadonlyRootfs') is True,
        'not_privileged': host.get('Privileged') is False,
        'all_capabilities_dropped': host.get('CapDrop') == ['ALL'],
        'no_new_privileges': host.get('SecurityOpt') == ['no-new-privileges:true'],
        'bounded_processes': host.get('PidsLimit') == 128,
        'bounded_memory': host.get('Memory') == 512 * 1024 * 1024,
        'bounded_cpu': host.get('NanoCpus') == 2_000_000_000,
        'ephemeral_hardened_tmp': host.get('Tmpfs') == {
            '/tmp': 'size=64m,mode=1777,noexec,nosuid,nodev'
        },
        'loopback_only_port': host.get('PortBindings') == {
            '8000/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8001'}]
        },
        'persistent_mounts_absent': container.get('Mounts') == [],
        'restart_policy': host.get('RestartPolicy') == {
            'Name': 'unless-stopped', 'MaximumRetryCount': 0
        },
    }
    if not all(posture.values()):
        raise ReleaseError(
            'Backend runtime is outside the reviewed isolation posture: '
            + json.dumps(posture, sort_keys=True)
        )
    return posture


def verify_public_release(config):
    return verify_public_release_version(config, config.release)


def verify_public_release_version(config, expected_release):
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
    if public_release != expected_release:
        raise ReleaseError(
            f'Public release mismatch: expected {expected_release}, '
            f'received {public_release!r}.'
        )


def verify_live_backend(config, environment, expected_image, *, audit_questions):
    wait_for_backend(config)
    verify_backend_runtime(config, expected_image)
    run_command(
        [
            'docker', 'compose', 'exec', '-T', 'backend', 'python', 'manage.py',
            'check', '--deploy', '--fail-level', 'WARNING',
        ],
        cwd=config.project_root,
        env=environment,
    )
    run_command(
        [
            'docker', 'compose', 'exec', '-T', 'backend', 'python', 'manage.py',
            'migrate', '--check',
        ],
        cwd=config.project_root,
        env=environment,
    )
    if audit_questions:
        run_command(
            [
                'docker', 'compose', 'exec', '-T', 'backend', 'python', 'manage.py',
                'audit_questions', '--database', '--fail-on-warnings',
            ],
            cwd=config.project_root,
            env=environment,
        )


def inspect_rollback_image(config, rollback_tag):
    payload = capture_command(
        ['docker', 'image', 'inspect', rollback_tag],
        cwd=config.project_root,
    )
    try:
        images = json.loads(payload)
        if not isinstance(images, list) or len(images) != 1:
            raise ValueError
        metadata = images[0]
        rollback_image = metadata['Id']
        image_config = metadata['Config']
        environment = image_config['Env']
        labels = image_config['Labels']
        if (
            not isinstance(environment, list)
            or not all(isinstance(value, str) for value in environment)
            or not isinstance(labels, dict)
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ReleaseError('The retained rollback image has invalid metadata.') from error
    if not IMAGE_ID_PATTERN.fullmatch(rollback_image):
        raise ReleaseError('The retained rollback tag has an invalid image ID.')
    releases = [
        value.split('=', 1)[1]
        for value in environment
        if value.startswith('PCEP_RELEASE=')
    ]
    if (
        len(releases) != 1
        or not RELEASE_PATTERN.fullmatch(releases[0])
        or labels.get('org.opencontainers.image.revision') != releases[0]
    ):
        raise ReleaseError(
            'The retained rollback image has inconsistent release metadata.'
        )
    return rollback_image, releases[0]


def restore_backend(config, environment, rollback_tag):
    """Restore and verify the exact pre-deploy image after a safe cutover failure."""
    rollback_image, expected_release = inspect_rollback_image(config, rollback_tag)

    run_command(
        ['docker', 'tag', rollback_image, BACKEND_IMAGE],
        cwd=config.project_root,
    )
    run_command(
        [
            'docker', 'compose', 'up', '-d', '--no-deps', '--no-build', 'backend',
        ],
        cwd=config.project_root,
        env=environment,
    )
    verify_live_backend(
        config,
        environment,
        rollback_image,
        audit_questions=False,
    )
    verify_public_release_version(config, expected_release)
    return expected_release


def _deploy_unlocked(config):
    root = config.project_root
    environment = release_environment(config)
    ensure_tracked_tree_is_clean(root)
    run_command(['docker', 'compose', 'config', '--quiet'], cwd=root, env=environment)
    verify_database_roles(config)

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
    if config.allow_migrations:
        run_reviewed_migrations(config, environment)

    try:
        run_command(
            ['docker', 'compose', 'up', '-d', '--no-deps', 'backend'],
            cwd=root,
            env=environment,
        )
        verify_live_backend(
            config,
            environment,
            candidate_image,
            audit_questions=True,
        )
    except (OSError, ReleaseError, subprocess.CalledProcessError) as error:
        if config.allow_migrations:
            raise ReleaseError(
                'Candidate failed after a migrated cutover. Automatic application '
                f'rollback is refused; review rollback image {rollback_tag} and '
                f'database backup {backup_path} before recovery. Failure: {error}'
            ) from error
        try:
            restored_release = restore_backend(
                config,
                environment,
                rollback_tag,
            )
        except (OSError, ReleaseError, subprocess.CalledProcessError) as rollback_error:
            raise ReleaseError(
                'Candidate failed after cutover and automatic rollback also failed. '
                f'Candidate failure: {error}; rollback failure: {rollback_error}; '
                f'retained image: {rollback_tag}; database backup: {backup_path}'
            ) from error
        raise ReleaseError(
            'Candidate failed after cutover; the previous backend release '
            f'{restored_release} was restored and verified. Failure: {error}'
        ) from error
    verify_public_release(config)
    return ReleaseResult(rollback_tag, backup_path, backup_sha256)


def deploy(config):
    try:
        with exclusive_operation_lock(
            'backend-maintenance',
            root=config.lock_root,
        ):
            return _deploy_unlocked(config)
    except OperationLockError as error:
        raise ReleaseError(str(error)) from error


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
