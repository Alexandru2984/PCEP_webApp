#!/usr/bin/env python3
"""Report or remove old atomic frontend/static release snapshots safely."""

import argparse
import os
from pathlib import Path
import re
import shutil


RELEASE_KINDS = {'frontend', 'static'}
SUFFIX_PATTERN = r'(?P<stamp>\d{8}T\d{6}Z)-(?P<identifier>[0-9a-f]{8})'


def keep_count(value):
    try:
        count = int(value)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError('keep must be an integer') from error
    if not 2 <= count <= 100:
        raise argparse.ArgumentTypeError('keep must be between 2 and 100')
    return count


def release_pattern(kind, location):
    if kind not in RELEASE_KINDS:
        raise ValueError('Release target must be named frontend or static.')
    prefix = rf'\.{re.escape(kind)}\.previous-' if location == 'previous' else rf'{re.escape(kind)}\.'
    return re.compile(rf'^{prefix}{SUFFIX_PATTERN}$')


def discover(parent, pattern):
    parent = Path(parent).absolute()
    if not parent.is_dir():
        raise ValueError(f'Release snapshot parent is not a directory: {parent}')
    found = []
    for path in parent.iterdir():
        if not pattern.fullmatch(path.name):
            continue
        if path.is_symlink() or not path.is_dir():
            raise ValueError(f'Unsafe matching release snapshot: {path}')
        found.append(path)
    return sorted(found, key=lambda path: path.name, reverse=True)


def retention_plan(target, backup_root, keep=5):
    target = Path(target).absolute()
    backup_root = Path(backup_root).absolute()
    if target.name not in RELEASE_KINDS:
        raise ValueError('Release target must be named frontend or static.')
    if not target.is_dir() or target.is_symlink():
        raise ValueError('Live release target must be a real directory.')
    if backup_root.resolve().is_relative_to(target.resolve()):
        raise ValueError('Backup root must be outside the live release target.')
    keep = keep_count(keep)

    previous = discover(target.parent, release_pattern(target.name, 'previous'))
    backups = discover(backup_root, release_pattern(target.name, 'backup'))
    return {
        'previous': {'keep': previous[:keep], 'remove': previous[keep:]},
        'backup': {'keep': backups[:keep], 'remove': backups[keep:]},
    }


def allocated_bytes(paths):
    """Count allocated bytes once per inode, including hard-linked snapshots."""
    seen = set()
    total = 0
    for root in paths:
        for directory, _, filenames in os.walk(root, followlinks=False):
            for name in filenames:
                path = Path(directory, name)
                if path.is_symlink():
                    continue
                stat = path.stat(follow_symlinks=False)
                inode = (stat.st_dev, stat.st_ino)
                if inode not in seen:
                    seen.add(inode)
                    total += stat.st_blocks * 512
    return total


def human_bytes(size):
    value = float(size)
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if value < 1024 or unit == 'TiB':
            return f'{value:.0f} {unit}' if unit == 'B' else f'{value:.1f} {unit}'
        value /= 1024


def remove_snapshot(path, parent, pattern):
    parent = Path(parent).resolve()
    path = Path(path)
    if (
        path.parent.resolve() != parent
        or not pattern.fullmatch(path.name)
        or path.is_symlink()
        or not path.is_dir()
    ):
        raise ValueError(f'Refusing to remove unsafe release snapshot: {path}')
    shutil.rmtree(path)


def execute(target, backup_root, keep=5, apply=False):
    target = Path(target).absolute()
    backup_root = Path(backup_root).absolute()
    plan = retention_plan(target, backup_root, keep)
    removals = plan['previous']['remove'] + plan['backup']['remove']
    reclaimable = allocated_bytes(removals)

    print(
        f'{"Applying" if apply else "Dry run:"} keep the newest {keep} complete '
        f'{target.name} snapshots in each location.'
    )
    for location, label in (('previous', 'rollback roots'), ('backup', 'backup copies')):
        group = plan[location]
        print(f'{label}: keep {len(group["keep"])}, remove {len(group["remove"])}')
        for path in group['remove']:
            print(f'  REMOVE {path}')
    print(f'Unique allocated space selected: {human_bytes(reclaimable)}')

    if not apply:
        print('Nothing removed. Re-run with --apply only after reviewing this list.')
        return plan

    previous_pattern = release_pattern(target.name, 'previous')
    backup_pattern = release_pattern(target.name, 'backup')
    for path in plan['previous']['remove']:
        remove_snapshot(path, target.parent, previous_pattern)
    for path in plan['backup']['remove']:
        remove_snapshot(path, backup_root, backup_pattern)
    print(f'Removed {len(removals)} reviewed release snapshots.')
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path, help='Live /.../frontend or /.../static root')
    parser.add_argument('--backup-root', type=Path, required=True)
    parser.add_argument('--keep', type=keep_count, default=5)
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Remove the listed snapshots; without this flag the command is read-only.',
    )
    args = parser.parse_args()
    try:
        execute(args.target, args.backup_root, args.keep, args.apply)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Release retention refused: {error}\n')


if __name__ == '__main__':
    main()
