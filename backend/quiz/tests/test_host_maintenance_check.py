import importlib.util
import os
from pathlib import Path
import stat
import subprocess

import pytest


spec = importlib.util.spec_from_file_location(
    'host_maintenance_check',
    Path(__file__).resolve().parents[3] / 'scripts/host_maintenance_check.py',
)
maintenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)


BOOT_A = '11111111-1111-4111-8111-111111111111'
BOOT_B = '22222222-2222-4222-8222-222222222222'
REVISION = 'a' * 40


def snapshot(**overrides):
    value = {
        'boot_id': BOOT_A,
        'checked_at': '2026-10-19T12:00:00Z',
        'expected_kernel': '7.0.0-38-generic',
        'reboot_required': True,
        'repository_commit': REVISION,
        'running_kernel': '7.0.0-29-generic',
    }
    value.update(overrides)
    return value


def payload(**overrides):
    value = snapshot(**overrides)
    return {'schema': 1, 'phase': 'preflight', 'preflight': value}


def result(returncode=0, stdout='', stderr=''):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_selects_newest_trusted_kernel_for_running_flavour(tmp_path):
    for release in ('7.0.0-29-generic', '7.0.0-38-generic', '7.0.0-40-lowlatency'):
        image = tmp_path / f'vmlinuz-{release}'
        image.write_bytes(b'kernel')
        image.chmod(0o644)

    assert maintenance.newest_installed_kernel(
        '7.0.0-29-generic',
        tmp_path,
        expected_uid=os.getuid(),
    ) == '7.0.0-38-generic'


def test_rejects_symlinked_or_writable_kernel_inventory(tmp_path):
    real = tmp_path / 'real-kernel'
    real.write_bytes(b'kernel')
    linked = tmp_path / 'vmlinuz-7.0.0-38-generic'
    linked.symlink_to(real)

    with pytest.raises(maintenance.HostMaintenanceError, match='symlink'):
        maintenance.newest_installed_kernel(
            '7.0.0-29-generic',
            tmp_path,
            expected_uid=os.getuid(),
        )

    linked.unlink()
    linked.write_bytes(b'kernel')
    linked.chmod(0o666)
    with pytest.raises(maintenance.HostMaintenanceError, match='unsafe metadata'):
        maintenance.newest_installed_kernel(
            '7.0.0-29-generic',
            tmp_path,
            expected_uid=os.getuid(),
        )


def test_private_state_round_trip_and_no_overwrite(tmp_path):
    tmp_path.chmod(0o700)
    state = tmp_path / 'pcep-host-maintenance-20261019T120000Z.json'
    evidence = payload()

    maintenance.write_state(
        state,
        evidence,
        replace=False,
        expected_uid=os.getuid(),
    )

    assert stat.S_IMODE(state.stat().st_mode) == 0o600
    assert maintenance.read_state(state, expected_uid=os.getuid()) == evidence
    with pytest.raises(maintenance.HostMaintenanceError, match='already exists'):
        maintenance.write_state(
            state,
            evidence,
            replace=False,
            expected_uid=os.getuid(),
        )


def test_state_rejects_unsafe_parent_file_and_schema(tmp_path):
    permissive = tmp_path / 'permissive'
    permissive.mkdir(mode=0o777)
    permissive.chmod(0o777)
    state = permissive / 'state.json'
    with pytest.raises(maintenance.HostMaintenanceError, match='owner-controlled'):
        maintenance.write_state(
            state,
            payload(),
            replace=False,
            expected_uid=os.getuid(),
        )

    private = tmp_path / 'private'
    private.mkdir(mode=0o700)
    real = private / 'real.json'
    real.write_text('{}')
    linked = private / 'linked.json'
    linked.symlink_to(real)
    with pytest.raises(maintenance.HostMaintenanceError, match='Cannot read'):
        maintenance.read_state(linked, expected_uid=os.getuid())

    invalid = private / 'invalid.json'
    invalid.write_text('{"schema":2}\n')
    invalid.chmod(0o600)
    with pytest.raises(maintenance.HostMaintenanceError, match='schema'):
        maintenance.read_state(invalid, expected_uid=os.getuid())

    evidence = private / 'evidence.json'
    maintenance.write_state(
        evidence,
        payload(),
        replace=False,
        expected_uid=os.getuid(),
    )
    os.link(evidence, private / 'evidence-hardlink.json')
    with pytest.raises(maintenance.HostMaintenanceError, match='owner-only'):
        maintenance.read_state(evidence, expected_uid=os.getuid())


@pytest.mark.parametrize(
    ('change', 'message'),
    (
        ({'boot_id': BOOT_A}, 'Boot ID'),
        ({'running_kernel': '7.0.0-37-generic'}, 'Running kernel'),
        ({'expected_kernel': '7.0.0-39-generic'}, 'inventory changed'),
        ({'repository_commit': 'b' * 40}, 'revision changed'),
        ({'reboot_required': True}, 'still reports'),
    ),
)
def test_postflight_rejects_missing_or_inconsistent_proof(change, message):
    before = snapshot()
    after = snapshot(
        boot_id=BOOT_B,
        running_kernel='7.0.0-38-generic',
        reboot_required=False,
    )
    after.update(change)

    with pytest.raises(maintenance.HostMaintenanceError, match=message):
        maintenance.validate_postflight(before, after)


def test_postflight_accepts_changed_boot_expected_kernel_and_same_revision():
    before = snapshot()
    after = snapshot(
        boot_id=BOOT_B,
        running_kernel='7.0.0-38-generic',
        reboot_required=False,
    )

    maintenance.validate_postflight(before, after)


def test_service_gate_rejects_active_or_failed_pcep_service():
    active_service = maintenance.PCEP_SERVICES[0]

    def active_runner(command, **_kwargs):
        if command[1:3] == ['show', '--property=ActiveState']:
            return result(stdout='active\n' if command[-1] == active_service else 'inactive\n')
        return result()

    with pytest.raises(maintenance.HostMaintenanceError, match='quiescent'):
        maintenance.require_service_state(runner=active_runner)

    failed_service = maintenance.PCEP_SERVICES[-1]

    def failed_runner(command, **_kwargs):
        if command[1:3] == ['show', '--property=ActiveState']:
            return result(stdout='inactive\n')
        if command[1:3] == ['is-failed', '--quiet']:
            return result(returncode=0 if command[-1] == failed_service else 1)
        return result()

    with pytest.raises(maintenance.HostMaintenanceError, match='is failed'):
        maintenance.require_service_state(runner=failed_runner)


def test_git_gate_requires_main_clean_and_exact_upstream(tmp_path):
    repository = tmp_path / 'repository'
    remote = tmp_path / 'remote.git'
    subprocess.run(
        ['/usr/bin/git', 'init', '--bare', remote],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        ['/usr/bin/git', 'init', '-b', 'main', repository],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            '/usr/bin/git',
            '-C',
            repository,
            'config',
            'user.email',
            'test@example.invalid',
        ],
        check=True,
    )
    subprocess.run(
        ['/usr/bin/git', '-C', repository, 'config', 'user.name', 'Test'],
        check=True,
    )
    subprocess.run(
        ['/usr/bin/git', '-C', repository, 'remote', 'add', 'origin', remote],
        check=True,
    )
    tracked = repository / 'tracked.txt'
    tracked.write_text('reviewed\n')
    subprocess.run(
        ['/usr/bin/git', '-C', repository, 'add', 'tracked.txt'],
        check=True,
    )
    subprocess.run(
        ['/usr/bin/git', '-C', repository, 'commit', '-m', 'initial'],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        ['/usr/bin/git', '-C', repository, 'push', '-u', 'origin', 'main'],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    head = subprocess.run(
        ['/usr/bin/git', '-C', repository, 'rev-parse', 'HEAD'],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert maintenance.git_revision(repository) == head
    tracked.write_text('drifted\n')
    with pytest.raises(maintenance.HostMaintenanceError, match='clean'):
        maintenance.git_revision(repository)
