#!/usr/bin/env bash
# Semantically validate every GitHub Actions workflow with a checksum-pinned linter.

set -euo pipefail

readonly ACTIONLINT_VERSION='1.7.12'
readonly ACTIONLINT_SHA256='8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8'
readonly ACTIONLINT_ARCHIVE="actionlint_${ACTIONLINT_VERSION}_linux_amd64.tar.gz"
readonly ACTIONLINT_URL="https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/${ACTIONLINT_ARCHIVE}"

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workflow_root="$root/.github/workflows"

die() { echo "workflow-check: $*" >&2; exit 1; }

[[ "$(uname -s)" == Linux ]] || die 'only the pinned Linux build is supported.'
case "$(uname -m)" in
    x86_64|amd64) ;;
    *) die 'only the pinned amd64 build is supported.' ;;
esac

for command in curl find install mktemp sha256sum shellcheck sort tar; do
    command -v "$command" >/dev/null 2>&1 || die "$command is required."
done

[[ -d "$workflow_root" && ! -L "$workflow_root" ]] \
    || die '.github/workflows must be a real directory.'

workflows=()
while IFS= read -r -d '' workflow; do
    name="${workflow##*/}"
    [[ ! -L "$workflow" && -f "$workflow" ]] \
        || die "workflow must be a regular file: $name"
    [[ "$name" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*\.ya?ml$ ]] \
        || die "unsafe or unsupported workflow filename: $name"
    workflows+=("$workflow")
done < <(find "$workflow_root" -mindepth 1 -maxdepth 1 -print0 | sort -z)
(( ${#workflows[@]} > 0 )) || die 'no workflow files found.'

stage="$(mktemp -d /tmp/pcep-actionlint.XXXXXX)"
cleanup() {
    case "$stage" in
        /tmp/pcep-actionlint.*) find "$stage" -depth -delete ;;
        *) echo "workflow-check: refusing unsafe temporary cleanup: $stage" >&2 ;;
    esac
}
trap cleanup EXIT

archive="$stage/$ACTIONLINT_ARCHIVE"
curl --fail --location --silent --show-error \
    --proto '=https' --tlsv1.2 \
    --output "$archive" "$ACTIONLINT_URL"
printf '%s  %s\n' "$ACTIONLINT_SHA256" "$archive" \
    | sha256sum --check --status \
    || die 'actionlint archive checksum mismatch.'

tar --extract --gzip --file="$archive" --directory="$stage" actionlint
chmod 0500 "$stage/actionlint"

# An explicit trusted empty config prevents repository-controlled ignore rules
# from suppressing findings. Pyflakes is disabled because workflows contain no
# Python integration; shellcheck remains mandatory for every shell run block.
install -m 0600 /dev/null "$stage/actionlint.yaml"
shellcheck_bin="$(command -v shellcheck)"
[[ "$shellcheck_bin" == /* ]] || die 'shellcheck must resolve to an absolute path.'

"$stage/actionlint" \
    -no-color \
    -config-file "$stage/actionlint.yaml" \
    -pyflakes '' \
    -shellcheck "$shellcheck_bin" \
    "${workflows[@]}"

printf 'Validated %d GitHub Actions workflow(s) with actionlint %s.\n' \
    "${#workflows[@]}" "$ACTIONLINT_VERSION"
