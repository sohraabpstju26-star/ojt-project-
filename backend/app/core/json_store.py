"""Crash-safe JSON persistence: .tmp -> fsync -> os.replace -> dir fsync."""
from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from typing import Any, Callable, Dict, List

from ..config import data_dir
from .file_lock import file_lock


class JSONStore:
    """A single JSON document with atomic, synchronised, locked writes."""

    def __init__(self, filename: str, default: Any):
        self.filename = filename
        self._default = default

    @property
    def path(self):
        return data_dir() / self.filename

    def _fresh_default(self) -> Any:
        return deepcopy(self._default)

    def read(self) -> Any:
        with file_lock(self.filename):
            return self._read_unlocked()

    def _read_unlocked(self) -> Any:
        path = self.path
        if not path.exists():
            return self._fresh_default()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return self._fresh_default()

    def write(self, value: Any) -> None:
        with file_lock(self.filename):
            self._write_unlocked(value)

    def _write_unlocked(self, value: Any) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(value, fh, indent=2, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
            try:
                dir_fd = os.open(str(path.parent), os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def mutate(self, fn: Callable[[Any], Any]) -> Any:
        """Atomically read, transform and persist. fn may mutate in place."""
        with file_lock(self.filename):
            data = self._read_unlocked()
            result = fn(data)
            self._write_unlocked(data)
            return result

    def append(self, record: Dict[str, Any]) -> Dict[str, Any]:
        self.mutate(lambda data: data.append(record))
        return record


class Stores:
    """Central registry of all JSON stores used by PAYFLOW."""

    def __init__(self) -> None:
        from ..config import DATA_FILES

        self.users = JSONStore("users.json", DATA_FILES["users.json"])
        self.accounts = JSONStore("accounts.json", DATA_FILES["accounts.json"])
        self.entries = JSONStore("entries.json", DATA_FILES["entries.json"])
        self.balances = JSONStore("balances.json", DATA_FILES["balances.json"])
        self.wallets = JSONStore("wallets.json", DATA_FILES["wallets.json"])
        self.beneficiaries = JSONStore("beneficiaries.json", DATA_FILES["beneficiaries.json"])
        self.requests = JSONStore("payment_requests.json", DATA_FILES["payment_requests.json"])
        self.merchants = JSONStore("merchants.json", DATA_FILES["merchants.json"])
        self.sessions = JSONStore("sessions.json", DATA_FILES["sessions.json"])
        self.notifications = JSONStore("notifications.json", DATA_FILES["notifications.json"])
        self.settings = JSONStore("settings.json", DATA_FILES["settings.json"])
        self.audit_logs = JSONStore("audit_logs.json", DATA_FILES["audit_logs.json"])
        self.security_events = JSONStore("security_events.json", DATA_FILES["security_events.json"])


stores = Stores()


def reset_stores() -> None:
    """Force fresh singleton (used by the test harness)."""
    global stores
    stores = Stores()
