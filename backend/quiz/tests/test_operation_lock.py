import importlib.util
import os
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'operation_lock',
    Path(__file__).resolve().parents[3] / 'scripts/operation_lock.py',
)
operation_lock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operation_lock)


def test_lock_is_private_and_refuses_a_concurrent_holder(tmp_path):
    root = tmp_path / 'locks'

    with operation_lock.exclusive_operation_lock('backend-maintenance', root=root):
        lock = root / 'backend-maintenance.lock'
        assert lock.read_text() == f'{os.getpid()}\n'
        assert lock.stat().st_mode & 0o777 == 0o600
        with pytest.raises(operation_lock.OperationLockError, match='already running'):
            with operation_lock.exclusive_operation_lock(
                'backend-maintenance',
                root=root,
            ):
                pytest.fail('A second holder must never enter the critical section.')


def test_lock_rejects_unsafe_names_and_roots(tmp_path):
    with pytest.raises(operation_lock.OperationLockError, match='safe label'):
        with operation_lock.exclusive_operation_lock('../escape', root=tmp_path):
            pass

    permissive = tmp_path / 'permissive'
    permissive.mkdir(mode=0o770)
    permissive.chmod(0o770)
    with pytest.raises(operation_lock.OperationLockError, match='private directory'):
        with operation_lock.exclusive_operation_lock('release-test', root=permissive):
            pass

    real = tmp_path / 'real'
    real.mkdir()
    linked = tmp_path / 'linked'
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(operation_lock.OperationLockError, match='symlink'):
        with operation_lock.exclusive_operation_lock('release-test', root=linked):
            pass
