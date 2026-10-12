#!/bin/bash
# Fetch and verify the pinned npm release into a complete staging directory.
set -euo pipefail
VERSION="0.29.4"
VERSION_SHA256="9d2e9b905735be07ee35c3132a0d7a6d5e2766e6c7ade3aeb0770b9b40adfec9"
TARBALL="https://registry.npmjs.org/pyodide/-/pyodide-${VERSION}.tgz"
INTEGRITY="sha512-tCseTsqU3kSxZIjkue5zXxTMNEwrKZwOIIEQRBA/VzHxFN1hoCxe4w41phfCdHd9it9RcCNQb5K/Re0InqMgvA=="
DEST="${PYODIDE_DEST:-$(cd "$(dirname "$0")/.." && pwd)/public/pyodide}"
FILES=(pyodide.js pyodide.asm.js pyodide.asm.wasm pyodide-lock.json python_stdlib.zip)
SHA256=(
    7be9e63eddf6bd8786a5ab71c8689c35731d187e3415fe58d7cb95423b50421a
    fe75e97ef2c7a10c41f23b96344c553c7c1c62821bb206080dbb24941c06d5f3
    10090fe41e019ae669d512e1f747021a8db2aaab0f6dd6f85fa9368c55d681e3
    14d2c2dba101277999e17135e653d8f15389ad1437f53eae213bf0c3cdff723d
    92cb24faa546818f3ef4050fd5bd2b6487bd2042efed2113af141d035f30efb4
)

die() {
    echo "$1" >&2
    exit 1
}

runtime_is_verified() {
    local root="$1"
    local actual file index
    local -a entries

    [ -d "$root" ] && [ ! -L "$root" ] || return 1
    [ -f "$root/VERSION" ] && [ ! -L "$root/VERSION" ] || return 1
    [ "$(<"$root/VERSION")" = "$VERSION" ] || return 1
    actual=$(sha256sum "$root/VERSION") || return 1
    actual=${actual%% *}
    [ "$actual" = "$VERSION_SHA256" ] || return 1

    for index in "${!FILES[@]}"; do
        file="${FILES[$index]}"
        [ -f "$root/$file" ] && [ ! -L "$root/$file" ] || return 1
        actual=$(sha256sum "$root/$file") || return 1
        actual=${actual%% *}
        [ "$actual" = "${SHA256[$index]}" ] || return 1
    done

    shopt -s dotglob nullglob
    entries=("$root"/*)
    shopt -u dotglob nullglob
    [ "${#entries[@]}" -eq "$((${#FILES[@]} + 1))" ] || return 1
}

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
for file in "${FILES[@]}"; do members+=("package/$file"); done
tar -xzf "$archive" -C "$stage/package" --strip-components=1 "${members[@]}"
for file in "${FILES[@]}"; do
    [ -f "$stage/package/$file" ] && [ ! -L "$stage/package/$file" ]
    mv "$stage/package/$file" "$stage/$file"
done
rm -rf "$stage/package" "$archive"
printf '%s\n' "$VERSION" > "$stage/VERSION"
runtime_is_verified "$stage" || die 'Extracted Pyodide runtime integrity check failed.'

if [ -e "$DEST" ] || [ -L "$DEST" ]; then
    previous_suffix=$(node -e "process.stdout.write(require('crypto').randomBytes(12).toString('hex'))")
    previous="${DEST}.previous.${previous_suffix}"
    [ ! -e "$previous" ] && [ ! -L "$previous" ] || die 'Refusing to overwrite a retained Pyodide runtime.'
    mv "$DEST" "$previous"
    if ! mv "$stage" "$DEST"; then mv "$previous" "$DEST"; exit 1; fi
    echo "Previous runtime retained at $previous"
else
    mv "$stage" "$DEST"
fi
echo "Pyodide $VERSION is ready."
