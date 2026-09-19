#!/usr/bin/env python3
"""Validate and publish a static directory with a reversible Linux atomic swap."""
import argparse
import ctypes
import errno
import os
from pathlib import Path
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit


class AssetReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('src'):
            self.paths.append(attrs['src'])
        if tag == 'link' and attrs.get('rel') in ('stylesheet', 'icon', 'manifest', 'modulepreload'):
            self.paths.append(attrs.get('href', ''))


def validate_release(source, kind='frontend'):
    if not source.is_dir():
        raise ValueError('Release source must be a directory.')
    for path in source.rglob('*'):
        if path.is_symlink() or path.name.startswith('.') or path.suffix in ('.pem', '.key'):
            raise ValueError(f'Unsafe file in release: {path.relative_to(source)}')
    required = ['admin/css/base.css', 'admin/js/core.js'] if kind == 'static' else [
        'index.html', 'sw.js', 'py-worker.js', 'manifest.webmanifest',
        'pyodide/VERSION', 'pyodide/pyodide.js', 'pyodide/pyodide.asm.js',
        'pyodide/pyodide.asm.wasm', 'pyodide/pyodide-lock.json', 'pyodide/python_stdlib.zip',
    ]
    for name in required:
        path = source / name
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f'Release is incomplete: {name}')
    if kind == 'frontend':
        parser = AssetReferences()
        parser.feed((source / 'index.html').read_text())
        for reference in parser.paths:
            parsed = urlsplit(reference)
            if parsed.netloc or parsed.scheme or parsed.path == '/u/script.js':
                continue
            path = (source / unquote(parsed.path).lstrip('/')).resolve()
            if not path.is_relative_to(source.resolve()) or not path.is_file():
                raise ValueError(f'Missing or unsafe HTML asset: {reference}')
        with (source / 'pyodide/pyodide.asm.wasm').open('rb') as runtime:
            if runtime.read(4) != b'\x00asm':
                raise ValueError('Invalid Python WebAssembly runtime.')


def exchange_directories(first, second):
    # Both directories are on the same filesystem. No interval without a live root.
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, 'renameat2', None)
    if rename is None:
        raise OSError(errno.ENOSYS, 'Atomic directory exchange is unavailable.')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(first), -100, os.fsencode(second), 2):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


def publish(source, target, backup_root=None, kind='frontend'):
    source, target = Path(source).resolve(), Path(target).absolute()
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise ValueError('The live root must be a real directory.')
    resolved_target = target.resolve()
    if source.is_relative_to(resolved_target) or resolved_target.is_relative_to(source):
        raise ValueError('Release source and live root must be separate directories.')
    validate_release(source, kind)
    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    stage = Path(tempfile.mkdtemp(prefix=f'.{target.name}.release-', dir=target.parent))
    swapped = False
    try:
        shutil.copytree(source, stage, dirs_exist_ok=True)
        # Old tabs can still import their original lazy chunks after an update.
        if kind == 'frontend' and (target / 'assets').is_dir():
            for asset in (target / 'assets').rglob('*'):
                if asset.is_file() and not asset.is_symlink():
                    destination = stage / asset.relative_to(target)
                    if not destination.exists():
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(asset, destination)
        validate_release(stage, kind)
        if backup_root and target.exists():
            backup_root = Path(backup_root).absolute()
            if backup_root.resolve().is_relative_to(resolved_target):
                raise ValueError('Backup root must be outside the live root.')
            backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copytree(target, backup_root / f'{target.name}.{stamp}')
        if target.exists():
            exchange_directories(stage, target)
            swapped = True
            previous = target.parent / f'.{target.name}.previous-{stamp}'
            try:
                stage.rename(previous)
            except OSError:
                # A successful swap remains successful; never delete the prior root.
                previous = stage
            return previous
        os.replace(stage, target)
        swapped = True
        return None
    finally:
        if not swapped and stage.exists():
            shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    parser.add_argument('--backup-root', type=Path)
    parser.add_argument('--kind', choices=('frontend', 'static'), default='frontend')
    args = parser.parse_args()
    try:
        previous = publish(args.source, args.target, args.backup_root, args.kind)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Publication failed before swap: {error}\n')
    print(f'Published complete {args.kind} release to {args.target}')
    if previous:
        print(f'Previous release retained at {previous}')


if __name__ == '__main__':
    main()
