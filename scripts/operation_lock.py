#!/usr/bin/env python3
"""Small fail-closed host locks for destructive PCEP maintenance operations."""

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import stat


LOCK_NAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9-]{0,63}$')


class OperationLockError(RuntimeError):
    pass


def default_lock_root():
    return Path('/run/lock') / f'pcep-{os.getuid()}'


def prepare_lock_root(path=None):
    root = Path(path if path is not None else default_lock_root()).absolute()
    if root.is_symlink():
        raise OperationLockError('Operation lock root must not be a symlink.')
    try:
        root.mkdir(mode=0o700, parents=False, exist_ok=True)
    except OSError as error:
        raise OperationLockError(
            f'Cannot create the operation lock root: {error}'
        ) from error
    try:
        root_stat = root.stat(follow_symlinks=False)
    except OSError as error:
        raise OperationLockError(
            f'Cannot inspect the operation lock root: {error}'
        ) from error
    if (
        not stat.S_ISDIR(root_stat.st_mode)
        or root_stat.st_uid != os.getuid()
        or root_stat.st_mode & 0o077
    ):
        raise OperationLockError(
            'Operation lock root must be a private directory owned by the invoking user.'
        )
    return root


@contextmanager
def exclusive_operation_lock(name, *, root=None):
    """Acquire one non-blocking lock in an owner-only host-global directory."""
    if not isinstance(name, str) or not LOCK_NAME_PATTERN.fullmatch(name):
        raise OperationLockError('Operation lock name must be a bounded safe label.')
    lock_root = prepare_lock_root(root)
    directory_flags = os.O_RDONLY
    if hasattr(os, 'O_DIRECTORY'):
        directory_flags |= os.O_DIRECTORY
    if hasattr(os, 'O_NOFOLLOW'):
        directory_flags |= os.O_NOFOLLOW
    try:
        root_descriptor = os.open(lock_root, directory_flags)
    except OSError as error:
        raise OperationLockError(f'Cannot open the operation lock root: {error}') from error

    descriptor = None
    try:
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, 'O_CLOEXEC'):
            flags |= os.O_CLOEXEC
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(
                f'{name}.lock',
                flags,
                0o600,
                dir_fd=root_descriptor,
            )
        except OSError as error:
            raise OperationLockError(f'Cannot open the operation lock: {error}') from error

        lock_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(lock_stat.st_mode)
            or lock_stat.st_uid != os.getuid()
            or lock_stat.st_mode & 0o077
        ):
            raise OperationLockError(
                'Operation lock must be a private regular file owned by the invoking user.'
            )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise OperationLockError(
                f'Another {name} operation is already running.'
            ) from error

        os.ftruncate(descriptor, 0)
        os.write(descriptor, f'{os.getpid()}\n'.encode())
        os.fsync(descriptor)
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(root_descriptor)
