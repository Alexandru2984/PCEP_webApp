#!/usr/bin/env bash
# Install dependencies without scripts, approve the exact inventory, then rebuild esbuild only.

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
npm_bin="${NPM:-npm}"
node_bin="${NODE:-node}"

command -v "$npm_bin" >/dev/null 2>&1 || {
    echo "frontend-install: npm executable not found: $npm_bin" >&2
    exit 1
}
command -v "$node_bin" >/dev/null 2>&1 || {
    echo "frontend-install: node executable not found: $node_bin" >&2
    exit 1
}

cd "$root"
"$npm_bin" ci --ignore-scripts
"$node_bin" scripts/check-install-scripts.mjs
"$npm_bin" rebuild esbuild --ignore-scripts=false
"$node_bin" -e \
    "require('esbuild').transformSync('const verified = true', { loader: 'js' })"

printf '%s\n' 'Installed dependencies with only esbuild@0.25.12 lifecycle code executed.'
