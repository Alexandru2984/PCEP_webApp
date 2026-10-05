#!/usr/bin/env bash
# Scan tracked files and reachable Git history without exposing local ignored secrets.

set -euo pipefail

DEFAULT_TRIVY_IMAGE='ghcr.io/aquasecurity/trivy:0.75.0@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa'
ROOT="${PCEP_REPOSITORY_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
TRIVY_IMAGE="${TRIVY_IMAGE:-$DEFAULT_TRIVY_IMAGE}"
scan_uid="$(id -u)"
scan_gid="$(id -g)"

die() { echo "secret-scan: $*" >&2; exit 1; }

[[ "$ROOT" == /* ]] || die 'repository root must be absolute.'
[[ -d "$ROOT/.git" ]] || die "not a Git worktree: $ROOT"
[[ "$TRIVY_IMAGE" != -* && -n "$TRIVY_IMAGE" ]] || die 'invalid Trivy image.'

canonical_root="$(git -C "$ROOT" rev-parse --show-toplevel)"
[[ "$canonical_root" == "$ROOT" ]] || die 'repository root is not canonical.'
[[ "$(git -C "$ROOT" rev-parse --is-shallow-repository)" == false ]] \
    || die 'refusing a shallow repository because history would be omitted.'

stage="$(mktemp -d /tmp/pcep-secret-scan.XXXXXX)"
cleanup() {
    case "$stage" in
        /tmp/pcep-secret-scan.*) find "$stage" -depth -delete ;;
        *) echo "secret-scan: refusing unsafe temporary cleanup: $stage" >&2 ;;
    esac
}
trap cleanup EXIT

tree="$stage/tree"
mkdir -m 0700 "$tree"

# Archive the current contents of every tracked path, including staged and
# unstaged edits, while deliberately excluding ignored/untracked .env files,
# operator configuration, build output and local assistant settings.
git -C "$ROOT" ls-files --cached -z \
    | while IFS= read -r -d '' path; do
        if [[ -e "$ROOT/$path" || -L "$ROOT/$path" ]]; then
            printf '%s\0' "$path"
        fi
    done \
    | tar --directory="$ROOT" --null --verbatim-files-from --no-recursion \
        --files-from=- --create --file="$stage/tracked.tar"
tar --extract --file="$stage/tracked.tar" --directory="$tree"

# Trivy's filesystem scanner does not traverse .git by default. A text patch
# makes all reachable committed history available to the same redacting secret
# detector without copying repository metadata or credentials into the scanner.
git -C "$ROOT" log --all --full-history --patch --diff-merges=separate --no-ext-diff \
    --format=fuller > "$tree/git-history.patch"

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
    --tmpfs /tmp:size=16m,noexec,nosuid,nodev \
    --volume "$tree:/workspace:ro" \
    "$TRIVY_IMAGE" fs \
        --scanners secret \
        --exit-code 1 \
        --no-progress \
        /workspace
