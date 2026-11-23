"""Inter-process and intra-process advisory locking built on fcntl.flock.

A thread-local re-entrancy guard prevents a thread from opening the same lock
file twice (a second flock on a separate fd would deadlock within one process).
"""
from __future__ import annotations

import fcntl
import threading
from contextlib import contextmanager
from typing import Iterator

from ..config import data_dir

_registry_guard = threading.Lock()
_registry: dict[str, threading.RLock] = {}
_thread = threading.local()


def _process_lock(name: str) -> threading.RLock:
    with _registry_guard:
        return _registry.setdefault(name, threading.RLock())


def _held() -> set[str]:
    if not hasattr(_thread, "held"):
        _thread.held = set()
    return _thread.held


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
