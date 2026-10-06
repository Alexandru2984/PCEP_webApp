#!/usr/bin/env bash
# Install dependencies without scripts, then verify the exact lifecycle inventory.

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

printf '%s\n' 'Installed dependencies with all lifecycle scripts disabled.'
