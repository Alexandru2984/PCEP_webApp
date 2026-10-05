#!/usr/bin/env bash
# Validate every repository-owned systemd unit and its adjacent drop-ins.

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unit_root="$root/ops/systemd"

die() { echo "systemd-check: $*" >&2; exit 1; }

command -v systemd-analyze >/dev/null 2>&1 \
    || die 'systemd-analyze is required.'
[[ -d "$unit_root" && ! -L "$unit_root" ]] \
    || die 'ops/systemd must be a real directory.'

while IFS= read -r -d '' entry; do
    relative="${entry#"$unit_root"/}"
    [[ ! -L "$entry" ]] || die "symlinks are not allowed: $relative"
    case "$relative" in
        pcep-*.service|pcep-*.timer)
            [[ "$relative" != */* && -f "$entry" ]] \
                || die "invalid unit entry: $relative"
            ;;
        pcep-*.service.d)
            [[ "$relative" != */* && -d "$entry" ]] \
                || die "invalid drop-in directory: $relative"
            ;;
        pcep-*.service.d/*.conf)
            [[ "$relative" != */*/* && -f "$entry" ]] \
                || die "invalid drop-in entry: $relative"
            ;;
        *) die "unexpected ops/systemd entry: $relative" ;;
    esac
done < <(find "$unit_root" -mindepth 1 -print0 | sort -z)

units=()
while IFS= read -r -d '' unit; do
    name="${unit##*/}"
    [[ "$name" =~ ^pcep-[a-z0-9-]+\.(service|timer)$ ]] \
        || die "unsafe unit filename: $name"
    units+=("$name")
done < <(
    find "$unit_root" -maxdepth 1 -type f \
        \( -name '*.service' -o -name '*.timer' \) -print0 \
        | sort -z
)
(( ${#units[@]} > 0 )) || die 'no systemd units found.'

dropin_count=0
while IFS= read -r -d '' dropin; do
    relative="${dropin#"$unit_root"/}"
    directory="${relative%%/*}"
    name="${relative##*/}"
    [[ "$directory" =~ ^pcep-[a-z0-9-]+\.service\.d$ ]] \
        || die "unsafe drop-in directory: $directory"
    [[ "$name" =~ ^[0-9][0-9]-[a-z0-9-]+\.conf$ ]] \
        || die "unsafe drop-in filename: $name"
    base="${directory%.d}"
    [[ -f "$unit_root/$base" && ! -L "$unit_root/$base" ]] \
        || die "drop-in has no repository-owned base unit: $relative"
    dropin_count=$((dropin_count + 1))
done < <(
    find "$unit_root" -mindepth 2 -maxdepth 2 -type f \
        -path '*.service.d/*.conf' -print0 \
        | sort -z
)

SYSTEMD_UNIT_PATH="$unit_root:/usr/lib/systemd/system:/lib/systemd/system" \
    systemd-analyze verify "${units[@]}"

printf 'Verified %d systemd unit(s) and %d drop-in(s).\n' \
    "${#units[@]}" "$dropin_count"
