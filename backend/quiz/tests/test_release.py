import importlib.util
import hashlib
import os
from pathlib import Path
import time

import pytest

spec = importlib.util.spec_from_file_location('publish_release', Path(__file__).resolve().parents[3] / 'scripts/publish_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.fixture(autouse=True)
def isolated_release_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(release, 'DEFAULT_LOCK_ROOT', tmp_path / 'locks')


def static_release(root, marker):
    for name in ['admin/css/base.css', 'admin/js/core.js']:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(marker)
    return root


def frontend_release(root, marker='public data'):
    for name in [
        'sw.js', 'runner.html', 'runner-bridge.js', 'py-worker.js',
        'manifest.webmanifest', '.well-known/security.txt', 'assets/new.js',
    ]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(marker)
    runtime_content = {
        'VERSION': b'0.29.4\n',
        'pyodide.js': marker.encode(),
        'pyodide.asm.js': marker.encode(),
        'pyodide.asm.wasm': b'\x00asm\x01\x00\x00\x00',
        'pyodide-lock.json': marker.encode(),
        'python_stdlib.zip': marker.encode(),
    }
    hashes = {}
    for name, content in runtime_content.items():
        path = root / 'pyodide' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        hashes[name] = hashlib.sha256(content).hexdigest()
    (root / 'index.html').write_text('<script src="/assets/new.js"></script>')
    return root, hashes


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


def test_publish_flushes_release_backup_and_parent_in_cutover_order(
    tmp_path, monkeypatch
):
    source = static_release(tmp_path / 'source', 'new')
    target = static_release(tmp_path / 'live', 'old')
    backup_root = tmp_path / 'backup'
    events = []
    real_exchange = release.exchange_directories

    monkeypatch.setattr(
        release,
        'fsync_tree',
        lambda path: events.append(('tree', Path(path).name)),
    )
    monkeypatch.setattr(
        release,
        'fsync_directory',
        lambda path: events.append(('directory', Path(path).name)),
    )

    def exchange(first, second):
        events.append(('exchange', Path(first).name, Path(second).name))
        real_exchange(first, second)

    monkeypatch.setattr(release, 'exchange_directories', exchange)

    release.publish(source, target, backup_root, kind='static')

    assert events[0][0] == 'tree'
    assert events[0][1].startswith('.live.release-')
    assert events[1][0] == 'tree'
    assert events[1][1].startswith('live.')
    assert events[2] == ('directory', 'backup')
    assert events[3][0] == 'exchange'
    assert events[4:] == [('directory', tmp_path.name)] * 2


def test_flush_failure_keeps_live_release_and_prevents_exchange(tmp_path, monkeypatch):
    source = static_release(tmp_path / 'source', 'new')
    target = static_release(tmp_path / 'live', 'old')
    monkeypatch.setattr(
        release,
        'fsync_tree',
        lambda _path: (_ for _ in ()).throw(OSError('storage failure')),
    )
    monkeypatch.setattr(
        release,
        'exchange_directories',
        lambda *_args: pytest.fail('exchange must not run after a flush failure'),
    )

    with pytest.raises(OSError, match='storage failure'):
        release.publish(source, target, kind='static')

    assert (target / 'admin/css/base.css').read_text() == 'old'
    assert not list(tmp_path.glob('.live.release-*'))


def test_parent_flush_failure_after_exchange_preserves_both_generations(
    tmp_path, monkeypatch
):
    source = static_release(tmp_path / 'source', 'new')
    target = static_release(tmp_path / 'live', 'old')
    monkeypatch.setattr(release, 'fsync_tree', lambda _path: None)
    monkeypatch.setattr(
        release,
        'fsync_directory',
        lambda _path: (_ for _ in ()).throw(OSError('parent storage failure')),
    )

    with pytest.raises(OSError, match='parent storage failure'):
        release.publish(source, target, kind='static')

    assert (target / 'admin/css/base.css').read_text() == 'new'
    retained = list(tmp_path.glob('.live.release-*'))
    assert len(retained) == 1
    assert (retained[0] / 'admin/css/base.css').read_text() == 'old'


def test_security_txt_seed_is_durable_before_publication_continues(
    tmp_path, monkeypatch
):
    source = tmp_path / 'source'
    disclosure = source / '.well-known/security.txt'
    disclosure.parent.mkdir(parents=True)
    disclosure.write_text('Contact: mailto:security@example.test\n')
    target = tmp_path / 'live'
    target.mkdir()
    events = []
    real_replace = os.replace

    monkeypatch.setattr(
        release,
        'fsync_regular_file',
        lambda path: events.append(('file', Path(path).name)),
    )
    monkeypatch.setattr(
        release,
        'fsync_directory',
        lambda path: events.append(('directory', Path(path).name)),
    )

    def replace(source_path, destination_path):
        events.append(('replace', Path(destination_path).name))
        real_replace(source_path, destination_path)

    monkeypatch.setattr(release.os, 'replace', replace)

    release.seed_rollback_security_txt(source, target)

    assert [event[0] for event in events] == ['file', 'replace', 'directory']
    assert events[0][1].startswith('.security.txt.')
    assert events[1:] == [
        ('replace', 'security.txt'),
        ('directory', '.well-known'),
    ]
    assert (target / '.well-known/security.txt').read_text() == disclosure.read_text()


def test_publish_refuses_a_concurrent_operation_for_the_same_target(
    tmp_path, monkeypatch
):
    source = static_release(tmp_path / 'source', 'new')
    target = static_release(tmp_path / 'live', 'old')
    lock_root = tmp_path / 'locks'
    monkeypatch.setattr(release, 'DEFAULT_LOCK_ROOT', lock_root)

    with release.exclusive_operation_lock(
        release.release_lock_name(target),
        root=lock_root,
    ):
        with pytest.raises(ValueError, match='already running'):
            release.publish(source, target, kind='static')

    assert (target / 'admin/css/base.css').read_text() == 'old'


def test_release_lock_collapses_parent_directory_aliases(tmp_path):
    real_parent = tmp_path / 'real'
    real_parent.mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(real_parent, target_is_directory=True)

    assert release.release_lock_name(real_parent / 'frontend') == (
        release.release_lock_name(alias / 'frontend')
    )


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


def test_frontend_allows_only_the_reviewed_well_known_resource(tmp_path, monkeypatch):
    source, hashes = frontend_release(tmp_path / 'source')
    monkeypatch.setattr(release, 'PYODIDE_SHA256', hashes)
    release.validate_release(source)

    (source / '.well-known/credentials').write_text('must not publish')
    with pytest.raises(ValueError, match='Unsafe file'):
        release.validate_release(source)

    (source / '.well-known/credentials').unlink()
    (source / 'assets/.private').mkdir()
    (source / 'assets/.private/token').write_text('must not publish')
    with pytest.raises(ValueError, match='Unsafe file'):
        release.validate_release(source)


def test_frontend_seeds_disclosure_into_backup_and_immediate_rollback(
    tmp_path, monkeypatch
):
    source, hashes = frontend_release(tmp_path / 'source', 'new')
    monkeypatch.setattr(release, 'PYODIDE_SHA256', hashes)
    target, _old_hashes = frontend_release(tmp_path / 'live', 'old')
    (target / '.well-known/security.txt').unlink()

    previous = release.publish(source, target, tmp_path / 'backup')

    expected = (source / '.well-known/security.txt').read_text()
    assert (target / '.well-known/security.txt').read_text() == expected
    assert (previous / '.well-known/security.txt').read_text() == expected
    assert next(
        (tmp_path / 'backup').glob('live.*/.well-known/security.txt')
    ).read_text() == expected


def test_frontend_refuses_unsafe_live_well_known_path(tmp_path, monkeypatch):
    source, hashes = frontend_release(tmp_path / 'source')
    monkeypatch.setattr(release, 'PYODIDE_SHA256', hashes)
    target = tmp_path / 'live'
    target.mkdir()
    (target / '.well-known').symlink_to(tmp_path)

    with pytest.raises(ValueError, match='real directory'):
        release.publish(source, target)

    assert not (target / 'index.html').exists()


def test_initial_publication_is_atomic_and_separate(tmp_path):
    source = static_release(tmp_path / 'source', 'new')
    target = tmp_path / 'live'
    assert release.publish(source, target, kind='static') is None
    assert (target / 'admin/js/core.js').read_text() == 'new'
    with pytest.raises(ValueError, match='separate'):
        release.publish(source, source, kind='static')


def test_frontend_keeps_old_lazy_chunks_and_rejects_missing_new_asset(tmp_path, monkeypatch):
    source, hashes = frontend_release(tmp_path / 'source')
    monkeypatch.setattr(release, 'PYODIDE_SHA256', hashes)
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


def test_frontend_bounds_old_chunks_and_keeps_the_previous_generation(tmp_path, monkeypatch):
    source, hashes = frontend_release(tmp_path / 'source', 'new release')
    monkeypatch.setattr(release, 'PYODIDE_SHA256', hashes)

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


def test_frontend_rejects_changed_or_unexpected_runtime_content(tmp_path, monkeypatch):
    source, hashes = frontend_release(tmp_path / 'source')
    monkeypatch.setattr(release, 'PYODIDE_SHA256', hashes)
    target = tmp_path / 'live'

    (source / 'pyodide/pyodide.js').write_text('changed after build')
    with pytest.raises(ValueError, match='integrity check failed'):
        release.publish(source, target)
    assert not target.exists()

    (source / 'pyodide/pyodide.js').write_text('public data')
    (source / 'pyodide/unexpected.js').write_text('unexpected')
    with pytest.raises(ValueError, match='Unexpected file'):
        release.publish(source, target)
    assert not target.exists()


def test_frontend_rejects_exposed_cache_generation(tmp_path, monkeypatch):
    source, hashes = frontend_release(tmp_path / 'source')
    monkeypatch.setattr(release, 'PYODIDE_SHA256', hashes)
    (source / 'pyodide.previous.audit').mkdir()

    with pytest.raises(ValueError, match='cache directory'):
        release.publish(source, tmp_path / 'live')
