import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TRIVY_REFERENCE = re.compile(
    r'ghcr\.io/aquasecurity/trivy:\d+\.\d+\.\d+@sha256:[0-9a-f]{64}'
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
