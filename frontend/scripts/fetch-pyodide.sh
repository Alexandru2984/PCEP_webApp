#!/bin/bash
# Fetch and verify the pinned npm release into a complete staging directory.
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
VERSION="0.29.4"
TARBALL="https://registry.npmjs.org/pyodide/-/pyodide-${VERSION}.tgz"
INTEGRITY="sha512-tCseTsqU3kSxZIjkue5zXxTMNEwrKZwOIIEQRBA/VzHxFN1hoCxe4w41phfCdHd9it9RcCNQb5K/Re0InqMgvA=="
MANIFEST="$SCRIPT_DIR/pyodide.sha256"
DEST="${PYODIDE_DEST:-$SCRIPT_DIR/../public/pyodide}"
ARCHIVE_FILES=(pyodide.js pyodide.asm.js pyodide.asm.wasm pyodide-lock.json python_stdlib.zip)
FILES=(VERSION "${ARCHIVE_FILES[@]}")
declare -A SHA256=()

die() {
    echo "$1" >&2
    exit 1
}

load_manifest() {
    local expected file extra known candidate

    [ -f "$MANIFEST" ] && [ ! -L "$MANIFEST" ] || die 'Pyodide hash manifest is missing or unsafe.'
    while read -r expected file extra; do
        [ -n "$expected" ] && [ -n "$file" ] && [ -z "${extra:-}" ] || die 'Malformed Pyodide hash manifest.'
        [[ "$expected" =~ ^[0-9a-f]{64}$ ]] || die 'Malformed Pyodide hash manifest.'
        known=false
        for candidate in "${FILES[@]}"; do
            if [ "$file" = "$candidate" ]; then known=true; break; fi
        done
        [ "$known" = true ] || die 'Unexpected file in Pyodide hash manifest.'
        [ -z "${SHA256[$file]+present}" ] || die 'Duplicate file in Pyodide hash manifest.'
        SHA256["$file"]="$expected"
    done < "$MANIFEST"
    [ "${#SHA256[@]}" -eq "${#FILES[@]}" ] || die 'Incomplete Pyodide hash manifest.'
}

runtime_is_verified() {
    local root="$1"
    local actual file
    local -a entries

    [ -d "$root" ] && [ ! -L "$root" ] || return 1
    for file in "${FILES[@]}"; do
        [ -f "$root/$file" ] && [ ! -L "$root/$file" ] || return 1
        actual=$(sha256sum "$root/$file") || return 1
        actual=${actual%% *}
        [ "$actual" = "${SHA256[$file]}" ] || return 1
    done
    [ "$(<"$root/VERSION")" = "$VERSION" ] || return 1

    shopt -s dotglob nullglob
    entries=("$root"/*)
    shopt -u dotglob nullglob
    [ "${#entries[@]}" -eq "${#FILES[@]}" ] || return 1
}

load_manifest

if [[ "$DEST" != /* ]]; then
    die 'PYODIDE_DEST must be an absolute, non-root path.'
fi
DEST=$(node -e "process.stdout.write(require('path').resolve(process.argv[1]))" "$DEST")
[ "$DEST" != "/" ] || die 'PYODIDE_DEST must be an absolute, non-root path.'
readonly DEST

if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != "--verify-only" ]; }; then
    die 'Usage: fetch-pyodide.sh [--verify-only]'
fi

if runtime_is_verified "$DEST"; then
    echo "Pyodide $VERSION is already verified."
    exit 0
fi

if [ "${1:-}" = "--verify-only" ]; then
    die "Pyodide $VERSION integrity verification failed."
fi

echo "Pyodide $VERSION cache is missing or invalid; replacing it."

mkdir -p "$(dirname "$DEST")"
stage=$(mktemp -d "${DEST}.fetch.XXXXXX")
readonly stage
cleanup() {
    if [ -d "$stage" ] && [[ "$stage" = "${DEST}.fetch."* ]]; then
        rm -rf -- "$stage"
    fi
}
trap cleanup EXIT
archive="$stage/pyodide.tgz"
echo "Fetching verified Pyodide $VERSION release"
curl --fail --silent --show-error --location --retry 2 --connect-timeout 10 \
    --max-time 120 --max-filesize 67108864 "$TARBALL" -o "$archive"
actual="sha512-$(node -e "process.stdout.write(require('crypto').createHash('sha512').update(require('fs').readFileSync(process.argv[1])).digest('base64'))" "$archive")"
if [ "$actual" != "$INTEGRITY" ]; then
    echo 'Pyodide release integrity check failed.' >&2
    exit 1
fi

mkdir "$stage/package"
members=()
for file in "${ARCHIVE_FILES[@]}"; do members+=("package/$file"); done
tar -xzf "$archive" -C "$stage/package" --strip-components=1 "${members[@]}"
for file in "${ARCHIVE_FILES[@]}"; do
    [ -f "$stage/package/$file" ] && [ ! -L "$stage/package/$file" ]
    mv "$stage/package/$file" "$stage/$file"
done
rm -rf "$stage/package" "$archive"
printf '%s\n' "$VERSION" > "$stage/VERSION"
runtime_is_verified "$stage" || die 'Extracted Pyodide runtime integrity check failed.'

if [ -e "$DEST" ] || [ -L "$DEST" ]; then
    previous_suffix=$(node -e "process.stdout.write(require('crypto').randomBytes(12).toString('hex'))")
    previous="$SCRIPT_DIR/../.pyodide-quarantine.${previous_suffix}"
    [ ! -e "$previous" ] && [ ! -L "$previous" ] || die 'Refusing to overwrite a retained Pyodide runtime.'
    mv "$DEST" "$previous"
    if ! mv "$stage" "$DEST"; then mv "$previous" "$DEST"; exit 1; fi
    rm -rf -- "$previous"
    echo 'Invalid cached runtime removed after verified replacement.'
else
    mv "$stage" "$DEST"
fi
echo "Pyodide $VERSION is ready."
