#!/usr/bin/env bash
# Download the minimal Pyodide runtime used by the in-browser code runner.
#
# Pyodide is ~12 MB and is NOT committed to git (see .gitignore). Run this once
# before `npm run build` (or `npm run dev`) so the files land in
# frontend/public/pyodide/ and get served same-origin at /pyodide/*.
#
#   npm run fetch-pyodide
#
# Only the core interpreter + stdlib are fetched — no scientific packages — which
# is all the PCEP snippets need. Pin the version here so builds are reproducible.
set -euo pipefail

VERSION="0.29.4"
BASE="https://cdn.jsdelivr.net/npm/pyodide@${VERSION}"
DEST="$(cd "$(dirname "$0")/.." && pwd)/public/pyodide"

# Runtime files needed by a classic worker that importScripts('pyodide.js').
FILES=(
  pyodide.js
  pyodide.asm.js
  pyodide.asm.wasm
  pyodide-lock.json
  python_stdlib.zip
)

mkdir -p "$DEST"
echo "Fetching Pyodide ${VERSION} -> ${DEST}"
for f in "${FILES[@]}"; do
  echo "  - ${f}"
  curl -fsSL "${BASE}/${f}" -o "${DEST}/${f}"
done

# Record the pinned version so the app can sanity-check / cache-bust if needed.
printf '%s\n' "${VERSION}" > "${DEST}/VERSION"
echo "Done. Pyodide ${VERSION} is ready at /pyodide/."
