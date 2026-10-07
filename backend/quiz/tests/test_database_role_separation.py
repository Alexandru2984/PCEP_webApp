import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'separate_database_roles',
    Path(__file__).resolve().parents[3] / 'scripts/separate_database_roles.py',
)
separation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(separation)


def config(tmp_path):
    return separation.release.ReleaseConfig(
        project_root=tmp_path,
        backup_root=tmp_path / 'backups',
        release='database-role-separation',
        public_health_url='https://invalid.local/',
    )


def test_role_migration_is_backup_and_restore_gated(tmp_path, monkeypatch):
    events = []
    monkeypatch.setattr(
        separation.release,
        'ensure_tracked_tree_is_clean',
        lambda *_args: events.append('clean'),
    )
    def verify_roles(*_args):
        events.append('roles')
        return {}

    monkeypatch.setattr(separation.release, 'verify_database_roles', verify_roles)
    backup = tmp_path / 'backup.sql.gz'
    monkeypatch.setattr(
        separation.release,
        'backup_database',
        lambda *_args, **_kwargs: events.append('backup') or (backup, 'digest'),
    )
    monkeypatch.setattr(
        separation.restore,
        'source_table_owner',
        lambda *_args: events.append('source-owner') or 'pcep_user',
    )
    image_id = f'sha256:{"a" * 64}'
    monkeypatch.setattr(
        separation.restore,
        'select_restore_image',
        lambda *_args: events.append('image') or (image_id, False),
    )
    monkeypatch.setattr(
        separation.restore,
        'validate_backup_in_isolation',
        lambda *_args: events.append('restore') or {'questions': 308},
    )

    def admin_sql(_config, sql):
        if 'CREATE TABLE public.pcep_forbidden_ddl_probe' in sql:
            events.append('ddl-denied')
            raise separation.release.ReleaseError('permission denied for schema public')
        events.append('migration-sql')
        return ''

    monkeypatch.setattr(separation.release, 'database_admin_sql', admin_sql)

    result = separation.execute(config(tmp_path), 'restore-check')

    assert result == (backup, 'digest')
    assert events.index('backup') < events.index('restore') < events.index('migration-sql')
    assert events[-2:] == ['roles', 'ddl-denied']


def test_already_separated_database_is_not_mutated(tmp_path, monkeypatch):
    monkeypatch.setattr(separation.release, 'ensure_tracked_tree_is_clean', lambda *_: None)
    monkeypatch.setattr(
        separation.restore, 'source_table_owner', lambda *_: 'pcep_owner'
    )
    monkeypatch.setattr(separation.release, 'verify_database_roles', lambda *_: {})
    monkeypatch.setattr(
        separation,
        'verify_app_cannot_create',
        lambda *_: None,
    )
    monkeypatch.setattr(
        separation.release,
        'backup_database',
        lambda *_args, **_kwargs: pytest.fail('No backup is needed for a no-op.'),
    )

    assert separation.execute(config(tmp_path), 'restore-check') is None


def test_partial_separation_aborts_instead_of_reapplying(tmp_path, monkeypatch):
    monkeypatch.setattr(separation.release, 'ensure_tracked_tree_is_clean', lambda *_: None)
    monkeypatch.setattr(
        separation.restore, 'source_table_owner', lambda *_: 'pcep_owner'
    )
    def reject_partial_state(*_args):
        raise separation.release.ReleaseError('unexpected grants')

    monkeypatch.setattr(
        separation.release, 'verify_database_roles', reject_partial_state
    )
    monkeypatch.setattr(
        separation.release,
        'backup_database',
        lambda *_args, **_kwargs: pytest.fail('Partial state must be reviewed first.'),
    )

    with pytest.raises(separation.release.ReleaseError, match='unexpected grants'):
        separation.execute(config(tmp_path), 'restore-check')


def test_role_migration_sql_sets_the_expected_security_boundaries():
    sql = separation.ROLE_MIGRATION_SQL
    assert 'REASSIGN OWNED BY pcep_user TO pcep_owner' in sql
    assert 'ALTER SCHEMA public OWNER TO pcep_owner' in sql
    assert 'REVOKE ALL ON DATABASE %I FROM pcep_user' in sql
    assert 'GRANT CONNECT ON DATABASE %I TO pcep_user' in sql
    assert 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES' in sql
    assert 'GRANT USAGE, SELECT ON ALL SEQUENCES' in sql
    assert 'ALTER ROLE pcep_migrator' in sql
    assert 'NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT' in sql
