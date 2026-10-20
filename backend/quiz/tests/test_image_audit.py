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

    assert len(python_matches) == 1
    assert len(node_matches) == 1
    assert set(re.findall(r'python-version: "([0-9.]+)"', workflows)) == {
        python_matches[0]
    }
    assert set(re.findall(r'node-version: "([0-9.]+)"', workflows)) == {
        node_matches[0]
    }


def test_postgres_base_image_is_immutable_and_synchronized_with_ci():
    dockerfile = (ROOT / 'docker' / 'postgres' / 'Dockerfile').read_text()
    ci = (ROOT / '.github' / 'workflows' / 'ci.yml').read_text()

    dockerfile_matches = POSTGRES_REFERENCE.findall(dockerfile)
    ci_matches = POSTGRES_REFERENCE.findall(ci)

    assert len(dockerfile_matches) == 2
    assert len(set(dockerfile_matches)) == 1
    assert ci_matches == dockerfile_matches[:1]


def test_dependabot_monitors_every_dockerfile_without_auto_merge():
    config = (ROOT / '.github' / 'dependabot.yml').read_text()

    assert config.count('package-ecosystem: "docker"') == 1
    assert 'package-ecosystem: "docker-compose"' not in config
    assert '- "/backend"' in config
    assert '- "/docker/postgres"' in config
    assert '- "/frontend"' in config
    assert 'auto-merge' not in config.lower()


def test_image_scanner_never_receives_the_docker_socket():
    sources = [
        (ROOT / 'Makefile').read_text(),
        (ROOT / 'scripts' / 'audit_docker_image.sh').read_text(),
    ]

    assert all('/var/run/docker.sock' not in source for source in sources)


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
