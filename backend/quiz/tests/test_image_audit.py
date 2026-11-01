import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TRIVY_REFERENCE = re.compile(
    r'ghcr\.io/aquasecurity/trivy:\d+\.\d+\.\d+@sha256:[0-9a-f]{64}'
)
PYTHON_REFERENCE = re.compile(
    r'python:(\d+\.\d+\.\d+)-slim@sha256:[0-9a-f]{64}'
)
NODE_REFERENCE = re.compile(
    r'node:(\d+\.\d+\.\d+)-alpine\d+\.\d+@sha256:[0-9a-f]{64}'
)
POSTGRES_REFERENCE = re.compile(
    r'postgres:16-alpine@sha256:[0-9a-f]{64}'
)


def test_trivy_defaults_are_immutable_and_synchronized():
    sources = (
        (ROOT / 'Makefile').read_text(),
        (ROOT / 'scripts' / 'audit_docker_image.sh').read_text(),
        (ROOT / 'scripts' / 'check_tracked_misconfigurations.sh').read_text(),
        (ROOT / 'scripts' / 'check_tracked_secrets.sh').read_text(),
    )

    references = [TRIVY_REFERENCE.findall(source) for source in sources]

    assert all(len(matches) == 1 for matches in references)
    assert len({matches[0] for matches in references}) == 1


def test_runtime_image_versions_match_ci_toolchains():
    backend_dockerfile = (ROOT / 'backend' / 'Dockerfile').read_text()
    frontend_dockerfile = (ROOT / 'frontend' / 'Dockerfile').read_text()
    workflows = ''.join(
        path.read_text() for path in (ROOT / '.github' / 'workflows').glob('*.yml')
    )

    python_matches = PYTHON_REFERENCE.findall(backend_dockerfile)
    node_matches = NODE_REFERENCE.findall(frontend_dockerfile)

    assert len(python_matches) == 2
    assert len(set(python_matches)) == 1
    assert len(node_matches) == 1
    assert set(re.findall(r'python-version: "([0-9.]+)"', workflows)) == {
        python_matches[0]
    }
    assert set(re.findall(r'node-version: "([0-9.]+)"', workflows)) == {
        node_matches[0]
    }
    assert all(
        line.startswith('FROM python:')
        for line in backend_dockerfile.splitlines()
        if line.startswith('FROM ')
    )
    assert all(
        line.startswith('FROM node:')
        for line in frontend_dockerfile.splitlines()
        if line.startswith('FROM ')
    )


def test_postgres_base_image_is_immutable_and_synchronized_with_ci():
    dockerfile = (ROOT / 'docker' / 'postgres' / 'Dockerfile').read_text()
    ci = (ROOT / '.github' / 'workflows' / 'ci.yml').read_text()

    dockerfile_matches = POSTGRES_REFERENCE.findall(dockerfile)
    ci_matches = POSTGRES_REFERENCE.findall(ci)

    assert len(dockerfile_matches) == 2
    assert len(set(dockerfile_matches)) == 1
    assert ci_matches == dockerfile_matches[:1]


def test_dependabot_updates_are_paused_without_losing_docker_coverage():
    config = (ROOT / '.github' / 'dependabot.yml').read_text()
    docker_config = config.split('package-ecosystem: "docker"', maxsplit=1)[1]

    assert config.count('package-ecosystem: "docker"') == 1
    assert 'package-ecosystem: "docker-compose"' not in config
    assert '- "/backend"' in config
    assert '- "/docker/postgres"' in config
    assert '- "/frontend"' in config
    assert 'auto-merge' not in config.lower()
    assert config.count('open-pull-requests-limit: 0') == 4
    assert config.count('dependency-name: "python"') == 1
    assert re.search(
        r'- dependency-name: "python"\s+'
        r'update-types:\s+'
        r'- "version-update:semver-minor"',
        docker_config,
    )


def test_image_scanner_never_receives_the_docker_socket():
    sources = [
        (ROOT / 'Makefile').read_text(),
        (ROOT / 'scripts' / 'audit_docker_image.sh').read_text(),
    ]

    assert all('/var/run/docker.sock' not in source for source in sources)


def test_misconfiguration_scanner_is_isolated_and_unsuppressible():
    script = (
        ROOT / 'scripts' / 'check_tracked_misconfigurations.sh'
    ).read_text()

    for control in (
        'git -C "$ROOT" ls-files --cached -z',
        '--network none',
        '--read-only',
        '--cap-drop ALL',
        '--security-opt no-new-privileges',
        '--volume "$tree:/workspace:ro"',
        '--config ""',
        '--ignorefile ""',
        '--skip-check-update',
        '--severity HIGH,CRITICAL',
        '--exit-code 1',
    ):
        assert control in script

    assert '/var/run/docker.sock' not in script


def test_image_scanner_is_unprivileged_and_reads_an_immutable_archive():
    script = (ROOT / 'scripts' / 'audit_docker_image.sh').read_text()

    for control in (
        'docker image save --output "$archive" "$image_id"',
        '--input /scan/image.tar',
        '--read-only',
        '--cap-drop ALL',
        '--security-opt no-new-privileges',
        '--volume "$archive:/scan/image.tar:ro"',
    ):
        assert control in script
