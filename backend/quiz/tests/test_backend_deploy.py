import importlib.util
import io
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'deploy_backend', Path(__file__).resolve().parents[3] / 'scripts/deploy_backend.py'
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

CANDIDATE_IMAGE = f'sha256:{"a" * 64}'


def candidate_capture(args):
    if args[:2] == ['git', 'status']:
        return ''
    if args[:3] == ['docker', 'image', 'inspect']:
        return CANDIDATE_IMAGE
    return 'abc123def456'


def config(tmp_path, **kwargs):
    values = {
        'project_root': tmp_path,
        'backup_root': tmp_path / 'backups',
        'release': 'abc123def456',
        'public_health_url': 'https://example.test/api/health/',
    }
    values.update(kwargs)
    return release.ReleaseConfig(**values)


def test_deploy_snapshots_and_backs_up_before_build(tmp_path, monkeypatch):
    events = []

    monkeypatch.setattr(
        release,
        'run_command',
        lambda args, **_kwargs: events.append(('run', tuple(args))),
    )

    def capture(args, **_kwargs):
        events.append(('capture', tuple(args)))
        return candidate_capture(args)

    monkeypatch.setattr(release, 'capture_command', capture)
    monkeypatch.setattr(
        release,
        'snapshot_running_backend',
        lambda *_args: events.append(('snapshot',)) or 'rollback:test',
    )
    monkeypatch.setattr(
        release,
        'backup_database',
        lambda *_args: events.append(('backup',)) or (tmp_path / 'backup.sql.gz', 'digest'),
    )
    monkeypatch.setattr(release, 'wait_for_backend', lambda *_: events.append(('healthy',)))
    monkeypatch.setattr(release, 'verify_public_release', lambda *_: events.append(('public',)))

    result = release.deploy(config(tmp_path))

    build = ('run', ('docker', 'compose', 'build', 'backend'))
    scan = ('run', ('make', 'audit-image', f'BACKEND_IMAGE={CANDIDATE_IMAGE}'))
    up = ('run', ('docker', 'compose', 'up', '-d', '--no-deps', 'backend'))
    assert events.index(('snapshot',)) < events.index(('backup',)) < events.index(build)
    assert events.index(build) < events.index(scan) < events.index(up)
    assert events.index(up) < events.index(('healthy',))
    assert events[-1] == ('public',)
    assert result.rollback_tag == 'rollback:test'
    assert any(
        event[0] == 'capture'
        and event[1][-2] == '-c'
        and 'DJANGO_SETTINGS_MODULE' in event[1][-1]
        for event in events
    )
    assert any(event[0] == 'run' and event[1][-2:] == ('migrate', '--check') for event in events)


def test_deploy_does_not_replace_backend_when_image_scan_fails(tmp_path, monkeypatch):
    commands = []

    def run(args, **_kwargs):
        commands.append(tuple(args))
        if args == ['make', 'audit-image', f'BACKEND_IMAGE={CANDIDATE_IMAGE}']:
            raise release.subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(release, 'run_command', run)
    monkeypatch.setattr(
        release,
        'capture_command',
        lambda args, **_kwargs: candidate_capture(args),
    )
    monkeypatch.setattr(release, 'snapshot_running_backend', lambda *_: 'rollback:test')
    monkeypatch.setattr(
        release, 'backup_database', lambda *_: (tmp_path / 'backup.sql.gz', 'digest')
    )

    with pytest.raises(release.subprocess.CalledProcessError):
        release.deploy(config(tmp_path))

    assert ('make', 'audit-image', f'BACKEND_IMAGE={CANDIDATE_IMAGE}') in commands
    assert ('docker', 'compose', 'up', '-d', '--no-deps', 'backend') not in commands


def test_reviewed_migrations_use_plan_instead_of_refusing_them(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(release, 'run_command', lambda args, **_: commands.append(tuple(args)))
    monkeypatch.setattr(
        release,
        'capture_command',
        lambda args, **_kwargs: candidate_capture(args),
    )
    monkeypatch.setattr(release, 'snapshot_running_backend', lambda *_: 'rollback:test')
    monkeypatch.setattr(
        release, 'backup_database', lambda *_: (tmp_path / 'backup.sql.gz', 'digest')
    )
    monkeypatch.setattr(release, 'wait_for_backend', lambda *_: None)
    monkeypatch.setattr(release, 'verify_public_release', lambda *_: None)

    release.deploy(config(tmp_path, allow_migrations=True))

    plan_index = next(
        index for index, command in enumerate(commands)
        if command[-2:] == ('showmigrations', '--plan')
    )
    up_index = commands.index(('docker', 'compose', 'up', '-d', '--no-deps', 'backend'))
    migrate_checks = [
        index for index, command in enumerate(commands)
        if command[-2:] == ('migrate', '--check')
    ]
    assert plan_index < up_index
    assert len(migrate_checks) == 1
    assert migrate_checks[0] > up_index


def test_snapshot_tag_is_verified_against_running_image(tmp_path, monkeypatch):
    commands = []

    def capture(args, **_kwargs):
        if args[:3] == ['docker', 'inspect', 'pcep_backend'] and '.State.Running' in args[-1]:
            return 'true healthy sha256:running'
        if args[:3] == ['docker', 'inspect', 'pcep_backend']:
            return 'oldrelease'
        if args[:4] == ['docker', 'image', 'inspect', 'sha256:running']:
            return 'sha256:running'
        if args[:3] == ['docker', 'image', 'inspect']:
            return 'sha256:running'
        raise AssertionError(args)

    monkeypatch.setattr(release, 'capture_command', capture)
    monkeypatch.setattr(
        release, 'run_command', lambda args, **_kwargs: commands.append(tuple(args))
    )

    tag = release.snapshot_running_backend(config(tmp_path), '20260928T010203Z')

    assert tag == 'pcep-backend-rollback:20260928T010203Z-release-oldrelease'
    assert commands == [
        ('docker', 'tag', 'sha256:running', tag),
    ]


def test_database_backup_is_private_atomic_and_verified(tmp_path, monkeypatch):
    database_dump = b'--\n-- PostgreSQL database dump\n--\nSELECT 1;\n'

    class FakeProcess:
        def __init__(self):
            self.stdout = io.BytesIO(database_dump)

        def wait(self, timeout=None):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr(release.subprocess, 'Popen', lambda *_args, **_kwargs: FakeProcess())

    path, digest = release.backup_database(config(tmp_path), '20260928T010203Z')

    assert path.name == 'pcep_db_20260928T010203Z.sql.gz'
    assert path.stat().st_mode & 0o777 == 0o600
    assert len(digest) == 64
    with release.gzip.open(path, 'rb') as backup:
        assert backup.read() == database_dump
    assert not list((tmp_path / 'backups').glob('.*.partial-*'))


@pytest.mark.parametrize('value', ['', 'dirty release', '../escape', 'x' * 65])
def test_release_label_is_bounded(value):
    with pytest.raises(release.ReleaseError):
        release.validate_release(value)


def test_deploy_refuses_tracked_changes_even_with_explicit_release(tmp_path, monkeypatch):
    monkeypatch.setattr(release, 'capture_command', lambda *_args, **_kwargs: ' M Makefile')
    monkeypatch.setattr(
        release,
        'run_command',
        lambda *_args, **_kwargs: pytest.fail('Docker must not run for a dirty tree.'),
    )

    with pytest.raises(release.ReleaseError, match='tracked uncommitted'):
        release.deploy(config(tmp_path))
