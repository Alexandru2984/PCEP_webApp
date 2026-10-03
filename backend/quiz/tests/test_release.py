import importlib.util
import os
from pathlib import Path
import time

import pytest

spec = importlib.util.spec_from_file_location('publish_release', Path(__file__).resolve().parents[3] / 'scripts/publish_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def static_release(root, marker):
    for name in ['admin/css/base.css', 'admin/js/core.js']:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(marker)
    return root


def test_publish_swaps_complete_directory_and_retains_previous(tmp_path):
    source = static_release(tmp_path / 'source', 'new')
    target = static_release(tmp_path / 'live', 'old')
    previous = release.publish(source, target, tmp_path / 'backup', kind='static')
    assert (target / 'admin/css/base.css').read_text() == 'new'
    assert target.stat().st_mode & 0o005 == 0o005
    assert (target / 'admin/css/base.css').stat().st_mode & 0o004
    assert (previous / 'admin/css/base.css').read_text() == 'old'
    assert next((tmp_path / 'backup').glob('*/admin/js/core.js')).read_text() == 'old'
    release.exchange_directories(previous, target)
    assert (target / 'admin/css/base.css').read_text() == 'old'


def test_failed_copy_or_swap_keeps_live_files(tmp_path, monkeypatch):
    source = static_release(tmp_path / 'source', 'new')
    target = static_release(tmp_path / 'live', 'old')
    monkeypatch.setattr(release, 'exchange_directories', lambda *_: (_ for _ in ()).throw(OSError('failed')))
    with pytest.raises(OSError):
        release.publish(source, target, kind='static')
    assert (target / 'admin/css/base.css').read_text() == 'old'
    assert not list(tmp_path.glob('.live.release-*'))


def test_rejects_incomplete_release_and_symlinks_before_touching_live(tmp_path):
    target = static_release(tmp_path / 'live', 'old')
    source = tmp_path / 'source'
    source.mkdir()
    with pytest.raises(ValueError, match='incomplete'):
        release.publish(source, target, kind='static')
    static_release(source, 'new')
    (source / 'secret').symlink_to('/etc/passwd')
    with pytest.raises(ValueError, match='Unsafe file'):
        release.publish(source, target, kind='static')
    assert (target / 'admin/css/base.css').read_text() == 'old'


def test_initial_publication_is_atomic_and_separate(tmp_path):
    source = static_release(tmp_path / 'source', 'new')
    target = tmp_path / 'live'
    assert release.publish(source, target, kind='static') is None
    assert (target / 'admin/js/core.js').read_text() == 'new'
    with pytest.raises(ValueError, match='separate'):
        release.publish(source, source, kind='static')


def test_frontend_keeps_old_lazy_chunks_and_rejects_missing_new_asset(tmp_path):
    source = tmp_path / 'source'
    for name in ['sw.js', 'py-worker.js', 'manifest.webmanifest', 'pyodide/VERSION', 'pyodide/pyodide.js', 'pyodide/pyodide.asm.js', 'pyodide/pyodide-lock.json', 'pyodide/python_stdlib.zip', 'assets/new.js']:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('public data')
    (source / 'pyodide/pyodide.asm.wasm').write_bytes(b'\x00asm\x01\x00\x00\x00')
    (source / 'index.html').write_text('<script src="/assets/new.js"></script>')
    target = tmp_path / 'live'
    (target / 'assets').mkdir(parents=True)
    (target / 'assets/old.js').write_text('old lazy chunk')
    previous = release.publish(source, target)
    assert (target / 'assets/old.js').read_text() == 'old lazy chunk'
    assert (target / 'assets/new.js').read_text() == 'public data'
    assert (previous / 'assets/old.js').exists()
    (source / 'assets/new.js').unlink()
    with pytest.raises(ValueError, match='Missing or unsafe HTML asset'):
        release.publish(source, target)
    assert (target / 'assets/new.js').exists()


def test_frontend_bounds_old_chunks_and_keeps_the_previous_generation(tmp_path):
    source = tmp_path / 'source'
    for name in ['sw.js', 'py-worker.js', 'manifest.webmanifest', 'pyodide/VERSION', 'pyodide/pyodide.js', 'pyodide/pyodide.asm.js', 'pyodide/pyodide-lock.json', 'pyodide/python_stdlib.zip', 'assets/new.js']:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('new release')
    (source / 'pyodide/pyodide.asm.wasm').write_bytes(b'\x00asm\x01\x00\x00\x00')
    (source / 'index.html').write_text('<script src="/assets/new.js"></script>')

    target = tmp_path / 'live'
    (target / 'assets').mkdir(parents=True)
    (target / 'index.html').write_text(
        '<script src="/assets/previous.js"></script>'
    )
    for name in ['previous.js', 'previous-lazy.js', 'recent.js', 'expired.js']:
        (target / 'assets' / name).write_text(name)
    previous_time = time.time() - 30 * 24 * 60 * 60
    os.utime(target / 'assets/previous.js', (previous_time, previous_time))
    os.utime(target / 'assets/previous-lazy.js', (previous_time, previous_time))
    expired_time = previous_time - 60
    os.utime(target / 'assets/expired.js', (expired_time, expired_time))

    previous = release.publish(source, target, asset_retention_days=7)

    assert (target / 'assets/new.js').is_file()
    assert (target / 'assets/previous.js').is_file()
    assert (target / 'assets/previous-lazy.js').is_file()
    assert (target / 'assets/recent.js').is_file()
    assert not (target / 'assets/expired.js').exists()
    assert (previous / 'assets/expired.js').is_file()


def test_rejects_invalid_asset_retention_before_touching_live(tmp_path):
    source = static_release(tmp_path / 'source', 'new')
    target = static_release(tmp_path / 'live', 'old')
    with pytest.raises(ValueError, match='retention days'):
        release.publish(source, target, kind='static', asset_retention_days=0)
    assert (target / 'admin/css/base.css').read_text() == 'old'
