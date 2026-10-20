#!/usr/bin/env bash
# Scan only tracked configuration with immutable, unsuppressible Trivy checks.

set -euo pipefail

DEFAULT_TRIVY_IMAGE='ghcr.io/aquasecurity/trivy:0.76.0@sha256:2416d1f74045b57274df1a340eee6b510cacd73c66a6ccb8da092b117eb7d222'
ROOT="${PCEP_REPOSITORY_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
TRIVY_IMAGE="${TRIVY_IMAGE:-$DEFAULT_TRIVY_IMAGE}"
scan_uid="$(id -u)"
scan_gid="$(id -g)"

die() { echo "misconfiguration-scan: $*" >&2; exit 1; }

[[ "$ROOT" == /* ]] || die 'repository root must be absolute.'
[[ -d "$ROOT/.git" ]] || die "not a Git worktree: $ROOT"
[[ "$TRIVY_IMAGE" != -* && -n "$TRIVY_IMAGE" ]] || die 'invalid Trivy image.'

canonical_root="$(git -C "$ROOT" rev-parse --show-toplevel)"
[[ "$canonical_root" == "$ROOT" ]] || die 'repository root is not canonical.'

stage="$(mktemp -d /tmp/pcep-misconfiguration-scan.XXXXXX)"
cleanup() {
    case "$stage" in
        /tmp/pcep-misconfiguration-scan.*) find "$stage" -depth -delete ;;
        *) echo "misconfiguration-scan: refusing unsafe temporary cleanup: $stage" >&2 ;;
    esac
}
trap cleanup EXIT

tree="$stage/tree"
mkdir -m 0700 "$tree"

# Use the current contents of tracked paths, including reviewed local edits, while
# excluding ignored credentials, backup data, build output and operator settings.
git -C "$ROOT" ls-files --cached -z \
    | while IFS= read -r -d '' path; do
        if [[ -e "$ROOT/$path" || -L "$ROOT/$path" ]]; then
            printf '%s\0' "$path"
        fi
    done \
    | tar --directory="$ROOT" --null --verbatim-files-from --no-recursion \
        --files-from=- --create --file="$stage/tracked.tar"
tar --extract --file="$stage/tracked.tar" --directory="$tree"

# The repository cannot weaken the scan through Trivy configuration, ignore files
# or custom policies. Embedded checks are versioned by the immutable scanner image.
docker run --rm \
    --network none \
    --read-only \
    --workdir / \
    --user "$scan_uid:$scan_gid" \
    --env HOME=/tmp \
    --cap-drop ALL \
    --security-opt no-new-privileges \
    --pids-limit 64 \
    --memory 512m \
    --tmpfs /tmp:size=32m,noexec,nosuid,nodev \
    --volume "$tree:/workspace:ro" \
    "$TRIVY_IMAGE" config \
        --config "" \
        --ignorefile "" \
        --skip-check-update \
        --severity HIGH,CRITICAL \
        --exit-code 1 \
        --disable-telemetry \
        --skip-version-check \
        --quiet \
        /workspace
