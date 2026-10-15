import importlib.util
import os
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'verify_operations_installation',
    Path(__file__).resolve().parents[3]
    / 'scripts/verify_operations_installation.py',
)
verification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verification)


def installation(tmp_path, include_offsite=False):
    project = tmp_path / 'project'
    source_root = project / 'ops/systemd'
    installed_root = tmp_path / 'systemd'
    enabled_root = installed_root / 'timers.target.wants'
    source_root.mkdir(parents=True)
    enabled_root.mkdir(parents=True)
    installed_root.chmod(0o755)
    enabled_root.chmod(0o755)

    all_sources = (
        verification.REQUIRED_UNITS | verification.OPTIONAL_OFFSITE_UNITS
    )
    installed = set(verification.REQUIRED_UNITS)
    if include_offsite:
        installed |= verification.OPTIONAL_OFFSITE_UNITS
    for name in all_sources:
        source = source_root / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f'reviewed {name}\n')
        source.chmod(0o644)
        if name in installed:
            target = installed_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.parent.chmod(0o755)
            target.write_text(source.read_text())
            target.chmod(0o644)

    for name in verification.REQUIRED_UNITS:
        if name.endswith('.timer'):
            (enabled_root / name).symlink_to(installed_root / name)

    seo_source = project / 'scripts/pcep-seo-pages.py'
    seo_source.parent.mkdir()
    seo_source.write_text('reviewed SEO generator\n')
    seo_source.chmod(0o755)
    seo_installed = tmp_path / 'pcep-seo-pages'
    seo_installed.write_text(seo_source.read_text())
    seo_installed.chmod(0o755)
    return project, installed_root, seo_installed


def verify(
    project,
    installed_root,
    seo_installed,
    active_timer_check=None,
    failed_service_check=None,
):
    return verification.verify_installation(
        project,
        installed_root,
        seo_installed,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
        active_timer_check=active_timer_check or (lambda _name: True),
        failed_service_check=failed_service_check or (lambda _name: False),
    )


def test_accepts_exact_required_policy_and_enabled_timers(tmp_path):
    project, installed_root, seo_installed = installation(tmp_path)

    assert verify(project, installed_root, seo_installed) == {
        'units': 12,
        'timers': 6,
        'offsite': False,
    }


def test_accepts_complete_optional_offsite_policy(tmp_path):
    project, installed_root, seo_installed = installation(
        tmp_path, include_offsite=True
    )

    result = verify(project, installed_root, seo_installed)

    assert result['units'] == 14
    assert result['offsite'] is True


def test_rejects_unit_generator_or_mode_drift(tmp_path):
    project, installed_root, seo_installed = installation(tmp_path)
    unit = installed_root / 'pcep-db-backup.service'
    unit.write_text('tampered\n')
    with pytest.raises(verification.OperationsInstallationError, match='hash'):
        verify(project, installed_root, seo_installed)

    unit.write_text((project / 'ops/systemd/pcep-db-backup.service').read_text())
    seo_installed.write_text('tampered\n')
    with pytest.raises(
        verification.OperationsInstallationError, match='generator hash'
    ):
        verify(project, installed_root, seo_installed)

    seo_installed.write_text('reviewed SEO generator\n')
    unit.chmod(0o664)
    with pytest.raises(verification.OperationsInstallationError, match='mode 0644'):
        verify(project, installed_root, seo_installed)


def test_rejects_disabled_or_redirected_timer(tmp_path):
    project, installed_root, seo_installed = installation(tmp_path)
    link = installed_root / 'timers.target.wants/pcep-db-backup.timer'
    link.unlink()
    with pytest.raises(verification.OperationsInstallationError, match='enabled'):
        verify(project, installed_root, seo_installed)

    wrong = installed_root / 'wrong.timer'
    wrong.write_text('wrong\n')
    link.symlink_to(wrong)
    with pytest.raises(verification.OperationsInstallationError, match='wrong unit'):
        verify(project, installed_root, seo_installed)


def test_rejects_inactive_timer_or_unexpected_activation(tmp_path):
    project, installed_root, seo_installed = installation(tmp_path)

    with pytest.raises(verification.OperationsInstallationError, match='active'):
        verify(
            project,
            installed_root,
            seo_installed,
            active_timer_check=lambda name: name != 'pcep-db-backup.timer',
        )

    wants = installed_root / 'multi-user.target.wants'
    wants.mkdir(mode=0o755)
    (wants / 'pcep-db-backup.service').symlink_to(
        installed_root / 'pcep-db-backup.service'
    )
    with pytest.raises(
        verification.OperationsInstallationError,
        match='Unexpected PCEP systemd activation',
    ):
        verify(project, installed_root, seo_installed)


def test_rejects_failed_scheduled_service_but_not_current_publisher(tmp_path):
    project, installed_root, seo_installed = installation(tmp_path)
    inspected = []

    def failed(name):
        inspected.append(name)
        return name == 'pcep-seo-pages.service'

    with pytest.raises(
        verification.OperationsInstallationError,
        match='Scheduled PCEP service is failed: pcep-seo-pages.service',
    ):
        verify(
            project,
            installed_root,
            seo_installed,
            failed_service_check=failed,
        )

    assert 'pcep-operations-health.service' not in inspected
    assert 'pcep-db-offsite.service' not in inspected


def test_rejects_partial_offsite_or_unexpected_pcep_unit(tmp_path):
    project, installed_root, seo_installed = installation(tmp_path)
    source = project / 'ops/systemd/pcep-db-offsite.service'
    installed = installed_root / 'pcep-db-offsite.service'
    installed.write_text(source.read_text())
    installed.chmod(0o644)
    with pytest.raises(verification.OperationsInstallationError, match='partially'):
        verify(project, installed_root, seo_installed)

    installed.unlink()
    rogue = installed_root / 'pcep-rogue.service'
    rogue.write_text('rogue\n')
    rogue.chmod(0o644)
    with pytest.raises(verification.OperationsInstallationError, match='Unexpected'):
        verify(project, installed_root, seo_installed)


def test_rejects_writable_policy_directories(tmp_path):
    project, installed_root, seo_installed = installation(tmp_path)
    installed_root.chmod(0o775)

    with pytest.raises(verification.OperationsInstallationError, match='writable'):
        verify(project, installed_root, seo_installed)

    installed_root.chmod(0o755)
    seo_installed.parent.chmod(0o777)
    with pytest.raises(verification.OperationsInstallationError, match='writable'):
        verify(project, installed_root, seo_installed)
