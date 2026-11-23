"""Inter-process and intra-process advisory locking.

On macOS/Linux this uses fcntl.flock (as required by the specification).
On Windows, where fcntl does not exist, an equivalent exclusive lock is built
from atomic O_CREAT|O_EXCL lock-file creation with stale-lock recovery.

A thread-local re-entrancy guard prevents a thread from opening the same lock
twice (a second flock on a separate fd would deadlock within one process).
"""
from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from typing import Iterator

from ..config import data_dir

try:
    import fcntl  # POSIX only
    _HAS_FCNTL = True
except ImportError:  # Windows
    fcntl = None  # type: ignore[assignment]
    _HAS_FCNTL = False

_registry_guard = threading.Lock()
_registry: dict[str, threading.RLock] = {}
_thread = threading.local()
_STALE_SECONDS = 120


def _process_lock(name: str) -> threading.RLock:
    with _registry_guard:
        return _registry.setdefault(name, threading.RLock())


def _held() -> set[str]:
    if not hasattr(_thread, "held"):
        _thread.held = set()
    return _thread.held


@contextmanager
def _windows_file_lock(path) -> Iterator[None]:
    """Atomic create-based lock with stale recovery (Windows fallback)."""
    deadline = time.monotonic() + 30
    while True:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode("ascii"))
            finally:
                os.close(fd)
            break
        except FileExistsError:
            try:
                if time.monotonic() - path.stat().st_mtime > _STALE_SECONDS:
                    path.unlink()
                    continue
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise TimeoutError(f"Timed out acquiring lock: {path}")
            time.sleep(0.02)
    try:
        yield
    finally:
        try:
            path.unlink()
        except OSError:
            pass


@contextmanager
def file_lock(name: str) -> Iterator[None]:
    """Acquire an exclusive advisory lock for the given logical resource."""
    held = _held()
    if name in held:
        # Re-entrant acquisition from the same thread: process RLock already held
        # and the same OS fd must not be re-locked.
        yield
        return

    lock_dir = data_dir() / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    path = lock_dir / f"{name}.lock"

    with _process_lock(name):
        if not _HAS_FCNTL:
            with _windows_file_lock(path):
                held.add(name)
                try:
                    yield
                finally:
                    held.discard(name)
            return

        with open(path, "a+") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            held.add(name)
            try:
                yield
            finally:
                held.discard(name)
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@contextmanager
def ledger_lock() -> Iterator[None]:
    """Single coarse lock serialising all ledger mutations and reads."""
    with file_lock("ledger"):
        yield
