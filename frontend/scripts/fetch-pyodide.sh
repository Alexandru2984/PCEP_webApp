#!/bin/bash
# Fetch and verify the pinned npm release into a complete staging directory.
set -euo pipefail
VERSION="0.29.4"
TARBALL="https://registry.npmjs.org/pyodide/-/pyodide-${VERSION}.tgz"
INTEGRITY="sha512-tCseTsqU3kSxZIjkue5zXxTMNEwrKZwOIIEQRBA/VzHxFN1hoCxe4w41phfCdHd9it9RcCNQb5K/Re0InqMgvA=="
DEST="${PYODIDE_DEST:-$(cd "$(dirname "$0")/.." && pwd)/public/pyodide}"
FILES=(pyodide.js pyodide.asm.js pyodide.asm.wasm pyodide-lock.json python_stdlib.zip)

if [ -f "$DEST/VERSION" ] && [ "$(cat "$DEST/VERSION")" = "$VERSION" ]; then
    complete=true
    for file in "${FILES[@]}"; do [ -s "$DEST/$file" ] || complete=false; done
    if $complete; then echo "Pyodide $VERSION is already complete."; exit 0; fi
fi

mkdir -p "$(dirname "$DEST")"
stage=$(mktemp -d "${DEST}.fetch.XXXXXX")
trap 'rm -rf "$stage"' EXIT
archive="$stage/pyodide.tgz"
echo "Fetching verified Pyodide $VERSION release"
curl --fail --silent --show-error --location --retry 2 --connect-timeout 10 --max-time 120 "$TARBALL" -o "$archive"
actual="sha512-$(node -e "process.stdout.write(require('crypto').createHash('sha512').update(require('fs').readFileSync(process.argv[1])).digest('base64'))" "$archive")"
if [ "$actual" != "$INTEGRITY" ]; then
    echo 'Pyodide release integrity check failed.' >&2
    exit 1
fi

mkdir "$stage/package"
tar -xzf "$archive" -C "$stage/package" --strip-components=1
for file in "${FILES[@]}"; do
    test -s "$stage/package/$file"
    mv "$stage/package/$file" "$stage/$file"
done
rm -rf "$stage/package" "$archive"
printf '%s\n' "$VERSION" > "$stage/VERSION"

if [ -d "$DEST" ]; then
    previous="${DEST}.previous.$(date +%s%N)"
    mv "$DEST" "$previous"
    if ! mv "$stage" "$DEST"; then mv "$previous" "$DEST"; exit 1; fi
    echo "Previous runtime retained at $previous"
else
    mv "$stage" "$DEST"
fi
echo "Pyodide $VERSION is ready."
