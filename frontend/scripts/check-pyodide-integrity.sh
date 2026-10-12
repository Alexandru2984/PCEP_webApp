#!/bin/bash
# Exercise the positive and negative cache-integrity paths without network access.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
FETCHER="$SCRIPT_DIR/fetch-pyodide.sh"
SOURCE="$SCRIPT_DIR/../public/pyodide"
test_root=$(mktemp -d "${TMPDIR:-/tmp}/pcep-pyodide-integrity.XXXXXX")
readonly test_root
cleanup() {
    find "$test_root" -depth -delete 2>/dev/null || true
}
trap cleanup EXIT

PYODIDE_DEST="$SOURCE" bash "$FETCHER" --verify-only >/dev/null

test_dest="$test_root/runtime"
mkdir "$test_dest"
cp -R "$SOURCE/." "$test_dest/"
printf 'tampered cache fixture\n' > "$test_dest/pyodide.js"
if PYODIDE_DEST="$test_dest" bash "$FETCHER" --verify-only >/dev/null 2>&1; then
    echo 'Modified Pyodide cache was accepted.' >&2
    exit 1
fi

cp "$SOURCE/pyodide.js" "$test_dest/pyodide.js"
unlink "$test_dest/pyodide.js"
ln -s "$SOURCE/pyodide.js" "$test_dest/pyodide.js"
if PYODIDE_DEST="$test_dest" bash "$FETCHER" --verify-only >/dev/null 2>&1; then
    echo 'Symlinked Pyodide cache entry was accepted.' >&2
    exit 1
fi

unlink "$test_dest/pyodide.js"
cp "$SOURCE/pyodide.js" "$test_dest/pyodide.js"
printf 'unexpected cache entry\n' > "$test_dest/unexpected.js"
if PYODIDE_DEST="$test_dest" bash "$FETCHER" --verify-only >/dev/null 2>&1; then
    echo 'Pyodide cache with an unexpected entry was accepted.' >&2
    exit 1
fi

echo 'Pyodide cache integrity checks passed.'
