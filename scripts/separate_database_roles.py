#!/usr/bin/env python3
"""One-time, backup-gated migration to PostgreSQL least-privilege roles."""

import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys


def load_script(name):
    path = Path(__file__).with_name(f'{name}.py')
    spec = importlib.util.spec_from_file_location(f'pcep_{name}', path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load {path.name}.')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


release = load_script('deploy_backend')
restore = load_script('database_restore_check')

ROLE_MIGRATION_SQL = f"""
BEGIN;
SELECT pg_advisory_xact_lock(hashtextextended('pcep-database-role-separation', 0));

DO $create_roles$
BEGIN
  IF NOT EXISTS (
    SELECT FROM pg_roles WHERE rolname = '{release.DATABASE_OWNER_ROLE}'
  ) THEN
    CREATE ROLE {release.DATABASE_OWNER_ROLE}
      NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
      NOREPLICATION NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (
    SELECT FROM pg_roles WHERE rolname = '{release.DATABASE_MIGRATOR_ROLE}'
  ) THEN
    CREATE ROLE {release.DATABASE_MIGRATOR_ROLE}
      NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
      NOREPLICATION NOBYPASSRLS;
  END IF;
END
$create_roles$;

ALTER ROLE {release.DATABASE_OWNER_ROLE}
  NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
  NOREPLICATION NOBYPASSRLS PASSWORD NULL;
ALTER ROLE {release.DATABASE_MIGRATOR_ROLE}
  NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
  NOREPLICATION NOBYPASSRLS PASSWORD NULL;
ALTER ROLE {release.APP_DATABASE_ROLE}
  LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT
  NOREPLICATION NOBYPASSRLS;

DO $remove_memberships$
DECLARE
  membership record;
BEGIN
  FOR membership IN
    SELECT granted.rolname AS granted_role, member.rolname AS member_role
    FROM pg_auth_members AS memberships
    JOIN pg_roles AS granted ON granted.oid = memberships.roleid
    JOIN pg_roles AS member ON member.oid = memberships.member
    WHERE (
      member.rolname IN (
        '{release.APP_DATABASE_ROLE}',
        '{release.DATABASE_OWNER_ROLE}',
        '{release.DATABASE_MIGRATOR_ROLE}'
      )
      AND NOT (
        granted.rolname = '{release.DATABASE_OWNER_ROLE}'
        AND member.rolname = '{release.DATABASE_MIGRATOR_ROLE}'
      )
    ) OR (
      granted.rolname = '{release.DATABASE_OWNER_ROLE}'
      AND member.rolname <> '{release.DATABASE_MIGRATOR_ROLE}'
    )
  LOOP
    EXECUTE format(
      'REVOKE %I FROM %I', membership.granted_role, membership.member_role
    );
  END LOOP;
END
$remove_memberships$;

GRANT {release.DATABASE_OWNER_ROLE} TO {release.DATABASE_MIGRATOR_ROLE};
REASSIGN OWNED BY {release.APP_DATABASE_ROLE} TO {release.DATABASE_OWNER_ROLE};
DO $database_owner$
BEGIN
  EXECUTE format(
    'ALTER DATABASE %I OWNER TO {release.DATABASE_OWNER_ROLE}', current_database()
  );
END
$database_owner$;
ALTER SCHEMA public OWNER TO {release.DATABASE_OWNER_ROLE};

DO $database_privileges$
BEGIN
  EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database());
  EXECUTE format(
    'REVOKE ALL ON DATABASE %I FROM {release.APP_DATABASE_ROLE}',
    current_database()
  );
  EXECUTE format(
    'REVOKE ALL ON DATABASE %I FROM {release.DATABASE_MIGRATOR_ROLE}',
    current_database()
  );
  EXECUTE format(
    'GRANT CONNECT ON DATABASE %I TO {release.APP_DATABASE_ROLE}',
    current_database()
  );
  EXECUTE format(
    'GRANT CONNECT ON DATABASE %I TO {release.DATABASE_MIGRATOR_ROLE}',
    current_database()
  );
END
$database_privileges$;

REVOKE ALL ON SCHEMA public FROM PUBLIC, {release.APP_DATABASE_ROLE};
GRANT USAGE ON SCHEMA public TO {release.APP_DATABASE_ROLE};
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {release.APP_DATABASE_ROLE};
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
  TO {release.APP_DATABASE_ROLE};
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {release.APP_DATABASE_ROLE};
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public
  TO {release.APP_DATABASE_ROLE};
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public
  FROM PUBLIC, {release.APP_DATABASE_ROLE};

ALTER DEFAULT PRIVILEGES FOR ROLE {release.DATABASE_OWNER_ROLE}
  IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE {release.DATABASE_OWNER_ROLE}
  IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES
  TO {release.APP_DATABASE_ROLE};
ALTER DEFAULT PRIVILEGES FOR ROLE {release.DATABASE_OWNER_ROLE}
  IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE {release.DATABASE_OWNER_ROLE}
  IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES
  TO {release.APP_DATABASE_ROLE};
ALTER DEFAULT PRIVILEGES FOR ROLE {release.DATABASE_OWNER_ROLE}
  IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM PUBLIC;

COMMIT;
"""


def verify_app_cannot_create(config):
    probe = 'pcep_forbidden_ddl_probe'
    try:
        release.database_admin_sql(
            config,
            f"""
BEGIN;
SET LOCAL ROLE {release.APP_DATABASE_ROLE};
CREATE TABLE public.{probe}(id integer);
ROLLBACK;
""",
        )
    except release.ReleaseError as error:
        if 'permission denied for schema public' not in str(error):
            raise release.ReleaseError(
                f'Application DDL-denial probe failed unexpectedly: {error}'
            ) from error
        return
    raise release.ReleaseError('Application role unexpectedly created a table.')


def execute(config, restore_container, fallback_image=None):
    release.ensure_tracked_tree_is_clean(config.project_root)
    expected_owner = restore.source_table_owner(config.database_container)
    if expected_owner == release.DATABASE_OWNER_ROLE:
        release.verify_database_roles(config)
        verify_app_cannot_create(config)
        print('Database roles already use the reviewed least-privilege posture.')
        return None

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup, digest = release.backup_database(
        config, stamp, filename_prefix='pcep_db_before_role_separation'
    )
    image_id, used_fallback = restore.select_restore_image(
        config.database_container, fallback_image
    )
    if used_fallback:
        print(
            'Exact live PostgreSQL image metadata is unavailable; using verified '
            f'fallback {fallback_image} ({image_id}).',
            flush=True,
        )
    metrics = restore.validate_backup_in_isolation(
        backup, restore_container, image_id, expected_owner
    )
    print(
        f'Pre-change backup restored in isolation: {backup} '
        f'({digest}; {metrics["questions"]} questions).',
        flush=True,
    )

    release.database_admin_sql(config, ROLE_MIGRATION_SQL)
    release.verify_database_roles(config)
    verify_app_cannot_create(config)
    print('Database role separation completed and verified.')
    print(f'Rollback backup: {backup}')
    print(f'Rollback backup SHA-256: {digest}')
    return backup, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--apply', action='store_true',
        help='Required confirmation for the ownership and privilege migration.',
    )
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--backup-root', type=Path, default=Path('/home/micu/backups/pcep'))
    parser.add_argument('--database-container', default='pcep_db')
    parser.add_argument('--restore-container', default='pcep_db_role_separation_restore')
    parser.add_argument('--fallback-image')
    args = parser.parse_args()
    if not args.apply:
        parser.error('--apply is required; no database changes were made')

    try:
        restore.validate_container_name(args.database_container, 'database')
        restore.validate_container_name(args.restore_container, 'restore')
        config = release.ReleaseConfig(
            project_root=args.project_root.resolve(),
            backup_root=args.backup_root,
            release='database-role-separation',
            public_health_url='https://invalid.local/',
            database_container=args.database_container,
        )
        execute(config, args.restore_container, args.fallback_image)
    except (
        OSError,
        ValueError,
        release.ReleaseError,
        restore.RestoreCheckError,
    ) as error:
        parser.exit(1, f'Database role separation failed: {error}\n')


if __name__ == '__main__':
    main()
