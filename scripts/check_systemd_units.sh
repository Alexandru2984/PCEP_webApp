#!/usr/bin/env bash
# Validate every repository-owned systemd unit and its adjacent drop-ins.

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unit_root="$root/ops/systemd"

die() { echo "systemd-check: $*" >&2; exit 1; }

for command in cp find install mktemp sort systemd-analyze; do
    command -v "$command" >/dev/null 2>&1 || die "$command is required."
done
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

# Verify against an isolated filesystem so production-only executable paths do
# not depend on what happens to exist on a CI runner. Empty executable stubs are
# never run; they let systemd validate the exact unit syntax and sandbox settings.
stage="$(mktemp -d /tmp/pcep-systemd-check.XXXXXX)"
cleanup() {
    case "$stage" in
        /tmp/pcep-systemd-check.*) find "$stage" -depth -delete ;;
        *) echo "systemd-check: refusing unsafe temporary cleanup: $stage" >&2 ;;
    esac
}
trap cleanup EXIT

stage_units="$stage/etc/systemd/system"
install -d -m 0755 \
    "$stage_units" \
    "$stage/home/micu/PCEP_webApp/backend/.venv/bin" \
    "$stage/usr/bin"
cp -a "$unit_root/." "$stage_units/"
install -m 0755 /dev/null \
    "$stage/home/micu/PCEP_webApp/backend/.venv/bin/python"
install -m 0755 /dev/null "$stage/usr/bin/install"

# Repository units legitimately depend on these host-provided units. Minimal
# fixtures make dependency resolution deterministic without importing a runner's
# mutable system unit inventory into the validation result.
printf '%s\n' \
    '[Service]' \
    'Type=oneshot' \
    'ExecStart=/home/micu/PCEP_webApp/backend/.venv/bin/python' \
    >"$stage_units/docker.service"
for target in basic.target network-online.target shutdown.target sysinit.target timers.target; do
    printf '%s\n' '[Unit]' "Description=Validation fixture for $target" \
        >"$stage_units/$target"
done

if ! diagnostics="$(
    SYSTEMD_UNIT_PATH='/etc/systemd/system' \
        systemd-analyze \
            --root="$stage" \
            --generators=no \
            --man=no \
            verify "${units[@]}" 2>&1
)"; then
    [[ -z "$diagnostics" ]] || printf '%s\n' "$diagnostics" >&2
    die 'systemd-analyze rejected the staged units.'
fi
if [[ -n "$diagnostics" ]]; then
    printf '%s\n' "$diagnostics" >&2
    die 'systemd-analyze reported diagnostics for the staged units.'
fi

printf 'Verified %d systemd unit(s) and %d drop-in(s).\n' \
    "${#units[@]}" "$dropin_count"
