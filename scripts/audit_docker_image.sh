#!/usr/bin/env bash
# Export an exact local image, then scan the archive without exposing Docker's
# root-equivalent daemon socket to the third-party scanner container.

set -euo pipefail

DEFAULT_TRIVY_IMAGE='ghcr.io/aquasecurity/trivy:0.75.0@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa'
image_reference="${1:-}"
trivy_image="${TRIVY_IMAGE:-$DEFAULT_TRIVY_IMAGE}"
cache="${TRIVY_CACHE:-/tmp/pcep-trivy-cache}"
scan_uid="$(id -u)"
scan_gid="$(id -g)"

die() { echo "image-audit: $*" >&2; exit 1; }

[[ -n "$image_reference" && "$image_reference" != -* ]] \
    || die 'an image reference is required.'
[[ -n "$trivy_image" && "$trivy_image" != -* ]] \
    || die 'the Trivy image reference is invalid.'
[[ "$cache" == /* ]] || die 'the Trivy cache path must be absolute.'
[[ ! -L "$cache" ]] || die 'the Trivy cache path must not be a symlink.'
mkdir -p -- "$cache"
[[ -d "$cache" ]] || die 'the Trivy cache path must be a directory.'
chmod 0700 "$cache"

image_id="$(docker image inspect "$image_reference" --format '{{.Id}}')"
[[ "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]] \
    || die 'Docker returned an invalid image ID.'

archive="$(mktemp /tmp/pcep-image-audit.XXXXXX.tar)"
cleanup() {
    case "$archive" in
        /tmp/pcep-image-audit.*.tar) rm -f -- "$archive" ;;
        *) echo "image-audit: refusing unsafe temporary cleanup: $archive" >&2 ;;
    esac
}
trap cleanup EXIT

# Resolve the caller's tag once, then export by immutable ID to prevent a tag
# update between inspection and scanning from changing the reviewed artifact.
docker image save --output "$archive" "$image_id"

docker run --rm \
    --read-only \
    --user "$scan_uid:$scan_gid" \
    --env HOME=/tmp \
    --cap-drop ALL \
    --security-opt no-new-privileges \
    --pids-limit 64 \
    --memory 1536m \
    --tmpfs /tmp:size=512m,noexec,nosuid,nodev \
    --volume "$archive:/scan/image.tar:ro" \
    --volume "$cache:/cache" \
    "$trivy_image" image \
        --input /scan/image.tar \
        --cache-dir /cache \
        --scanners vuln \
        --severity HIGH,CRITICAL \
        --ignore-unfixed \
        --exit-code 1 \
        --no-progress \
        --disable-telemetry \
        --skip-version-check
