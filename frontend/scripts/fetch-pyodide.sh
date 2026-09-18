#!/bin/bash
# Download the pinned core runtime into a complete staging directory first.
set -euo pipefail
VERSION="0.29.4"
BASE="https://cdn.jsdelivr.net/npm/pyodide@${VERSION}"
DEST="$(cd "$(dirname "$0")/.." && pwd)/public/pyodide"
FILES=(pyodide.js pyodide.asm.js pyodide.asm.wasm pyodide-lock.json python_stdlib.zip)
if [ -f "$DEST/VERSION" ] && [ "$(cat "$DEST/VERSION")" = "$VERSION" ]; then
    complete=true
    for file in "${FILES[@]}"; do [ -s "$DEST/$file" ] || complete=false; done
    if $complete; then echo "Pyodide $VERSION is already complete."; exit 0; fi
fi
mkdir -p "$(dirname "$DEST")"
stage=$(mktemp -d "${DEST}.fetch.XXXXXX")
trap 'rm -rf "$stage"' EXIT
for file in "${FILES[@]}"; do
    echo "Fetching Pyodide $VERSION: $file"
    curl --fail --silent --show-error --location --retry 2 --connect-timeout 10 --max-time 120 "${BASE}/${file}" -o "$stage/$file"
    test -s "$stage/$file"
done
printf '%s\n' "$VERSION" > "$stage/VERSION"
# Build inputs only; frontend publication handles the live atomic swap.
if [ -d "$DEST" ]; then
    previous="${DEST}.previous.$(date +%s%N)"
    mv "$DEST" "$previous"
    if ! mv "$stage" "$DEST"; then mv "$previous" "$DEST"; exit 1; fi
    echo "Previous runtime retained at $previous"
else
    mv "$stage" "$DEST"
fi
echo "Pyodide $VERSION is ready."
