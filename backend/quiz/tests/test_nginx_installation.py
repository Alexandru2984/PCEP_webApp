import importlib.util
import os
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'verify_nginx_installation',
    Path(__file__).resolve().parents[3] / 'scripts/verify_nginx_installation.py',
)
verification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verification)


def installation(tmp_path):
    project = tmp_path / 'project'
    nginx = tmp_path / 'etc-nginx'
    (project / 'nginx/snippets').mkdir(parents=True)
    (nginx / 'sites-available').mkdir(parents=True)
    (nginx / 'sites-enabled').mkdir()
    (nginx / 'snippets').mkdir()

    for live_name, source_name in verification.VHOSTS.items():
        content = f'vhost {live_name}\n'
        source = project / 'nginx' / source_name
        available = nginx / 'sites-available' / live_name
        source.write_text(content)
        available.write_text(content)
        source.chmod(0o644)
        available.chmod(0o644)
        (nginx / 'sites-enabled' / live_name).symlink_to(available)

    for name in verification.SNIPPETS:
        content = f'snippet {name}\n'
        source = project / 'nginx/snippets' / name
        installed = nginx / 'snippets' / name
        source.write_text(content)
        installed.write_text(content)
        source.chmod(0o644)
        installed.chmod(0o644)

    return project, nginx


def verify(project, nginx):
    return verification.verify_installation(
        project,
        nginx,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )


def test_accepts_exact_files_and_active_symlinks(tmp_path):
    project, nginx = installation(tmp_path)

    assert verify(project, nginx) == {'vhosts': 2, 'snippets': 5}


def test_rejects_inactive_regular_copy(tmp_path):
    project, nginx = installation(tmp_path)
    enabled = nginx / 'sites-enabled/pcep.micutu.com'
    enabled.unlink()
    enabled.write_text('copied configuration\n')
    enabled.chmod(0o644)

    with pytest.raises(ValueError, match='must be a symlink'):
        verify(project, nginx)


def test_rejects_vhost_or_snippet_drift(tmp_path):
    project, nginx = installation(tmp_path)
    (nginx / 'sites-available/pcep.micutu.com').write_text('drifted\n')

    with pytest.raises(ValueError, match='vhost hash'):
        verify(project, nginx)

    (nginx / 'sites-available/pcep.micutu.com').write_text('vhost pcep.micutu.com\n')
    (nginx / 'snippets/pcep-csp.conf').write_text('drifted\n')
    with pytest.raises(ValueError, match='snippet hash'):
        verify(project, nginx)


def test_rejects_wrong_target_mode_and_ownership(tmp_path):
    project, nginx = installation(tmp_path)
    enabled = nginx / 'sites-enabled/pcep.micutu.com'
    enabled.unlink()
    enabled.symlink_to(nginx / 'sites-available/pcep-runner.micutu.com')
    with pytest.raises(ValueError, match='does not target'):
        verify(project, nginx)

    enabled.unlink()
    enabled.symlink_to(nginx / 'sites-available/pcep.micutu.com')
    installed = nginx / 'snippets/pcep-proxy.conf'
    installed.chmod(0o664)
    with pytest.raises(ValueError, match='mode 0644'):
        verify(project, nginx)

    installed.chmod(0o644)
    with pytest.raises(ValueError, match='ownership'):
        verification.verify_installation(
            project,
            nginx,
            expected_uid=os.getuid() + 1,
            expected_gid=os.getgid(),
        )
