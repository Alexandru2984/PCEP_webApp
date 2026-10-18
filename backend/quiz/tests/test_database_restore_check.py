import hashlib
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


spec = importlib.util.spec_from_file_location(
    'database_restore_check',
    Path(__file__).resolve().parents[3] / 'scripts/database_restore_check.py',
)
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


def complete_backup(root, stamp):
    path = root / f'pcep_db_daily_{stamp}.sql.gz'
    path.write_bytes(stamp.encode())
    path.chmod(0o600)
    checksum = path.with_name(f'{path.name}.sha256')
    checksum.write_text(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n')
    checksum.chmod(0o600)
    return path, checksum


def valid_metrics(**overrides):
    metrics = {
        'questions': 308,
        'choices': 1232,
        'migrations': 29,
        'question_owner': 'pcep_user',
        'unique_index_valid': True,
        'invalid_choice_counts': 0,
        'invalid_correct_counts': 0,
    }
    metrics.update(overrides)
    return metrics


def test_selects_newest_complete_private_verified_backup(tmp_path):
    root = tmp_path / 'daily'
    root.mkdir(mode=0o700)
    older = complete_backup(root, '20261001T010000Z')
    newer = complete_backup(root, '20261002T010000Z')

    assert restore.select_latest_backup(root) == newer
    assert older[0].exists()


def test_backup_selection_rejects_public_root_and_corruption(tmp_path):
    root = tmp_path / 'daily'
    root.mkdir(mode=0o755)
    path, _checksum = complete_backup(root, '20261001T010000Z')
    with pytest.raises(restore.RestoreCheckError, match='group or others'):
        restore.select_latest_backup(root)

    root.chmod(0o700)
    path.write_text('corrupt')
    with pytest.raises(restore.RestoreCheckError, match='checksum'):
        restore.select_latest_backup(root)


def test_source_image_must_be_an_immutable_docker_id():
    good_id = f"sha256:{'a' * 64}"

    def good_runner(_command, **_kwargs):
        return SimpleNamespace(stdout=f'{good_id}\n')

    assert restore.source_image_id('pcep_db', good_runner) == good_id

    def bad_runner(_command, **_kwargs):
        return SimpleNamespace(stdout='postgres:latest\n')

    with pytest.raises(restore.RestoreCheckError, match='invalid image ID'):
        restore.source_image_id('pcep_db', bad_runner)


def fallback_config(**overrides):
    config = {
        'User': 'postgres',
        'Entrypoint': ['docker-entrypoint.sh'],
        'Cmd': ['postgres'],
        'Labels': {'com.pcep.restore-profile': restore.RESTORE_IMAGE_PROFILE},
        'Env': ['PG_MAJOR=16', 'PG_VERSION=16.15', 'PGDATA=/var/lib/postgresql/data'],
    }
    config.update(overrides)
    return config


def test_uses_exact_live_image_when_its_metadata_is_available():
    live_id = f"sha256:{'d' * 64}"

    def runner(command, **_kwargs):
        if command[:4] == ['docker', 'inspect', '--type', 'container']:
            return SimpleNamespace(returncode=0, stdout=f'{live_id}\n', stderr='')
        if command[:4] == ['docker', 'image', 'inspect', live_id]:
            return SimpleNamespace(returncode=0, stdout=f'{live_id}\n', stderr='')
        raise AssertionError(command)

    assert restore.select_restore_image('pcep_db', 'unused:fallback', runner) == (
        live_id,
        False,
    )


def test_uses_reviewed_compatible_fallback_when_live_metadata_is_missing():
    live_id = f"sha256:{'d' * 64}"
    fallback_id = f"sha256:{'e' * 64}"
    fallback = 'pcep_webapp-postgres:16.15-alpine3.24'

    def runner(command, **_kwargs):
        if command[:4] == ['docker', 'inspect', '--type', 'container']:
            return SimpleNamespace(returncode=0, stdout=f'{live_id}\n', stderr='')
        if command[:4] == ['docker', 'image', 'inspect', live_id]:
            return SimpleNamespace(returncode=1, stdout='', stderr='missing')
        if command[:3] == ['docker', 'exec', '--user']:
            return SimpleNamespace(
                returncode=0,
                stdout='postgres (PostgreSQL) 16.15\n',
                stderr='',
            )
        if command[:4] == ['docker', 'image', 'inspect', fallback]:
            return SimpleNamespace(returncode=0, stdout=f'{fallback_id}\n', stderr='')
        if command[:4] == ['docker', 'image', 'inspect', fallback_id]:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(fallback_config()),
                stderr='',
            )
        raise AssertionError(command)

    assert restore.select_restore_image('pcep_db', fallback, runner) == (
        fallback_id,
        True,
    )


def test_reads_and_bounds_the_live_table_owner():
    def owner_runner(command, **kwargs):
        assert command[:5] == [
            'docker', 'exec', '--interactive', '--user', 'postgres'
        ]
        assert "'public.quiz_question'::regclass" in kwargs['input_text']
        return SimpleNamespace(returncode=0, stdout='pcep_owner\n', stderr='')

    assert restore.source_table_owner('pcep_db', owner_runner) == 'pcep_owner'

    def unexpected_runner(_command, **_kwargs):
        return SimpleNamespace(returncode=0, stdout='postgres\n', stderr='')

    with pytest.raises(restore.RestoreCheckError, match='unexpected owner'):
        restore.source_table_owner('pcep_db', unexpected_runner)


def test_refuses_unreviewed_or_secret_bearing_fallbacks():
    fallback_id = f"sha256:{'f' * 64}"

    def runner_for(config):
        def runner(command, **_kwargs):
            output = (
                fallback_id
                if command[-2:] == ['--format', '{{.Id}}']
                else json.dumps(config)
            )
            return SimpleNamespace(returncode=0, stdout=output, stderr='')

        return runner

    wrong_profile = fallback_config(Labels={'com.pcep.restore-profile': 'unknown'})
    with pytest.raises(restore.RestoreCheckError, match='restore profile'):
        restore.verify_fallback_restore_image(
            'reviewed:tag', '16', runner_for(wrong_profile)
        )

    secret = fallback_config(Env=['PG_MAJOR=16', 'POSTGRES_PASSWORD=embedded'])
    with pytest.raises(restore.RestoreCheckError, match='runtime secrets'):
        restore.verify_fallback_restore_image('reviewed:tag', '16', runner_for(secret))

    mismatch = fallback_config(Env=['PG_MAJOR=17'])
    with pytest.raises(restore.RestoreCheckError, match='major version'):
        restore.verify_fallback_restore_image(
            'reviewed:tag', '16', runner_for(mismatch)
        )


def test_restore_container_command_is_ephemeral_and_isolated():
    image_id = f"sha256:{'b' * 64}"
    ownership_token = 'a' * 32
    command = restore.docker_run_command(
        'pcep_db_restore_check', image_id, ownership_token
    )

    assert command[-1] == image_id
    assert command[command.index('--network') + 1] == 'none'
    assert command[command.index('--user') + 1] == 'postgres'
    assert command[command.index('--cap-drop') + 1] == 'ALL'
    assert 'no-new-privileges:true' in command
    assert '/var/lib/postgresql/data:rw,noexec,nosuid,nodev,size=256m,mode=0700,uid=70,gid=70' in command
    assert 'PCEP_OWNER_ROLE=pcep_owner' in command
    assert 'PCEP_MIGRATOR_USER=pcep_migrator' in command
    assert f'{restore.RESTORE_CONTAINER_LABEL}={ownership_token}' in command
    assert not {'--publish', '-p', '--volume', '-v'} & set(command)


def test_readiness_waits_for_final_postgres_and_a_successful_sql_probe():
    calls = []
    process_names = iter(['docker-entrypoint.sh', 'postgres', 'postgres'])
    probe_results = iter(
        [
            SimpleNamespace(
                returncode=1,
                stdout='',
                stderr='the database system is starting up',
            ),
            SimpleNamespace(returncode=0, stdout='1\n', stderr=''),
        ]
    )
    sleeps = []

    def runner(command, **_kwargs):
        calls.append(command)
        if command[-2:] == ['cat', '/proc/1/comm']:
            return SimpleNamespace(
                returncode=0,
                stdout=f'{next(process_names)}\n',
                stderr='',
            )
        if command[-2:] == ['--command', 'SELECT 1']:
            return next(probe_results)
        raise AssertionError(command)

    restore.wait_for_database(
        'pcep_db_restore_check',
        runner=runner,
        clock=lambda: 0,
        sleeper=lambda seconds: sleeps.append(seconds),
    )

    assert sleeps == [1, 1]
    assert sum(call[-2:] == ['cat', '/proc/1/comm'] for call in calls) == 3
    assert sum(call[-2:] == ['--command', 'SELECT 1'] for call in calls) == 2
    assert all('pg_isready' not in call for call in calls)


def test_readiness_timeout_includes_bounded_container_logs():
    moments = iter([0, 0, 2])

    def runner(command, **_kwargs):
        if command[:2] == ['docker', 'logs']:
            return SimpleNamespace(
                returncode=0,
                stdout='',
                stderr='final startup diagnostic',
            )
        return SimpleNamespace(
            returncode=0,
            stdout='docker-entrypoint.sh\n',
            stderr='',
        )

    with pytest.raises(
        restore.RestoreCheckError,
        match='final startup diagnostic',
    ):
        restore.wait_for_database(
            'pcep_db_restore_check',
            timeout_seconds=1,
            runner=runner,
            clock=lambda: next(moments),
            sleeper=lambda _seconds: None,
        )


def test_disposable_container_is_removed_after_a_failed_check():
    calls = []
    image_id = f"sha256:{'c' * 64}"
    container_id = 'd' * 64
    ownership_token = 'a' * 32

    def runner(command, **_kwargs):
        calls.append(command)
        if command[:3] == ['docker', 'inspect', '--type']:
            metadata = (
                json.dumps({restore.RESTORE_CONTAINER_LABEL: ownership_token})
                + f'\n{image_id}\n{container_id}\n'
            )
            return SimpleNamespace(returncode=0, stdout=metadata, stderr='')
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    with pytest.raises(RuntimeError, match='synthetic failure'):
        with restore.disposable_restore_container(
            'pcep_db_restore_check',
            image_id,
            runner,
            ownership_token=ownership_token,
        ):
            raise RuntimeError('synthetic failure')

    assert calls[-1] == ['docker', 'rm', '--force', container_id]


def test_start_timeout_removes_a_created_owned_container():
    calls = []
    image_id = f"sha256:{'c' * 64}"
    container_id = 'e' * 64
    ownership_token = 'b' * 32

    def runner(command, **_kwargs):
        calls.append(command)
        if command[:2] == ['docker', 'run']:
            raise restore.RestoreCheckError('Command timed out: docker')
        if command[:3] == ['docker', 'inspect', '--type']:
            metadata = (
                json.dumps({restore.RESTORE_CONTAINER_LABEL: ownership_token})
                + f'\n{image_id}\n{container_id}\n'
            )
            return SimpleNamespace(returncode=0, stdout=metadata, stderr='')
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    with pytest.raises(restore.RestoreCheckError, match='timed out'):
        with restore.disposable_restore_container(
            'pcep_db_restore_check',
            image_id,
            runner,
            ownership_token=ownership_token,
        ):
            pytest.fail('startup failure must not yield')

    assert calls[-1] == ['docker', 'rm', '--force', container_id]


def test_start_failure_does_not_remove_another_runs_same_named_container(capsys):
    calls = []
    image_id = f"sha256:{'c' * 64}"
    ownership_token = 'c' * 32
    other_token = 'd' * 32

    def runner(command, **_kwargs):
        calls.append(command)
        if command[:2] == ['docker', 'run']:
            raise restore.RestoreCheckError('name is already in use')
        if command[:3] == ['docker', 'inspect', '--type']:
            metadata = (
                json.dumps({restore.RESTORE_CONTAINER_LABEL: other_token})
                + f'\n{image_id}\n{"f" * 64}\n'
            )
            return SimpleNamespace(returncode=0, stdout=metadata, stderr='')
        raise AssertionError(command)

    with pytest.raises(restore.RestoreCheckError, match='already in use'):
        with restore.disposable_restore_container(
            'pcep_db_restore_check',
            image_id,
            runner,
            ownership_token=ownership_token,
        ):
            pytest.fail('startup failure must not yield')

    assert not any(command[:3] == ['docker', 'rm', '--force'] for command in calls)
    assert 'owned by another run' in capsys.readouterr().err


@pytest.mark.parametrize(
    ('labels', 'actual_image', 'container_id', 'message'),
    [
        ({'owner': 'other'}, None, 'f' * 64, 'owned by another run'),
        (
            {restore.RESTORE_CONTAINER_LABEL: 'true'},
            f"sha256:{'a' * 64}",
            'f' * 64,
            'another image',
        ),
        (
            {restore.RESTORE_CONTAINER_LABEL: 'true'},
            None,
            '../unsafe',
            'ID is invalid',
        ),
    ],
)
def test_cleanup_requires_exact_label_image_and_immutable_id(
    labels,
    actual_image,
    container_id,
    message,
):
    image_id = f"sha256:{'c' * 64}"
    ownership_token = 'e' * 32
    if labels.get(restore.RESTORE_CONTAINER_LABEL) == 'true':
        labels = {restore.RESTORE_CONTAINER_LABEL: ownership_token}
    metadata = (
        json.dumps(labels)
        + f'\n{actual_image or image_id}\n{container_id}\n'
    )

    def runner(command, **_kwargs):
        assert command[:3] == ['docker', 'inspect', '--type']
        return SimpleNamespace(returncode=0, stdout=metadata, stderr='')

    with pytest.raises(restore.RestoreCheckError, match=message):
        restore.owned_restore_container_id(
            'pcep_db_restore_check',
            image_id,
            ownership_token,
            runner,
        )


def test_restore_check_refuses_a_concurrent_run(tmp_path, monkeypatch):
    lock_root = tmp_path / 'locks'
    monkeypatch.setattr(
        restore,
        '_execute_unlocked',
        lambda *_args, **_kwargs: pytest.fail(
            'A locked restore check must not inspect backups or Docker.'
        ),
    )

    with restore.exclusive_operation_lock(
        'database-restore-check',
        root=lock_root,
    ):
        with pytest.raises(restore.RestoreCheckError, match='already running'):
            restore.execute(
                tmp_path,
                'pcep_db',
                'pcep_db_restore_check',
                lock_root=lock_root,
            )


@pytest.mark.parametrize('token', ['', 'short', '../escape', 'g' * 32, 'a' * 33])
def test_rejects_unsafe_restore_ownership_tokens(token):
    with pytest.raises(restore.RestoreCheckError, match='ownership token'):
        restore.validate_ownership_token(token)


def test_validates_restored_schema_and_question_integrity():
    metrics = valid_metrics()
    assert restore.validate_metrics(json.dumps(metrics)) == metrics

    failures = [
        ({'questions': 0}, 'questions'),
        ({'migrations': True}, 'migrations'),
        ({'question_owner': 'postgres'}, 'wrong owner'),
        ({'unique_index_valid': False}, 'index'),
        ({'invalid_choice_counts': 1}, 'invalid_choice_counts'),
        ({'invalid_correct_counts': 1}, 'invalid_correct_counts'),
    ]
    for override, message in failures:
        with pytest.raises(restore.RestoreCheckError, match=message):
            restore.validate_metrics(json.dumps(valid_metrics(**override)))

    owner_metrics = valid_metrics(question_owner='pcep_owner')
    assert restore.validate_metrics(
        json.dumps(owner_metrics), expected_owner='pcep_owner'
    ) == owner_metrics


@pytest.mark.parametrize('name', ['', '-bad', 'bad/name', 'bad name'])
def test_rejects_unsafe_container_names(name):
    with pytest.raises(restore.RestoreCheckError, match='container name'):
        restore.validate_container_name(name, 'test')


def test_success_status_is_atomic_private_and_contains_no_backup_metadata(tmp_path):
    status = tmp_path / 'last-success.json'
    moment = datetime(2026, 10, 13, 8, 30, tzinfo=timezone.utc)

    restore.write_success_status(status, now=moment)

    assert status.stat().st_mode & 0o777 == 0o600
    assert json.loads(status.read_text()) == {
        'completed_at': '2026-10-13T08:30:00Z',
        'schema': 1,
    }
    assert list(tmp_path.glob('.*.partial-*')) == []


def test_success_status_rejects_an_unsafe_parent_or_existing_symlink(tmp_path):
    unsafe_parent = tmp_path / 'unsafe'
    unsafe_parent.mkdir(mode=0o777)
    unsafe_parent.chmod(0o777)
    with pytest.raises(restore.RestoreCheckError, match='not writable'):
        restore.write_success_status(unsafe_parent / 'status.json')

    target = tmp_path / 'target'
    target.write_text('preserve')
    status = tmp_path / 'status.json'
    status.symlink_to(target)
    with pytest.raises(restore.RestoreCheckError, match='real file'):
        restore.write_success_status(status)
    assert target.read_text() == 'preserve'
    assert os.path.islink(status)
