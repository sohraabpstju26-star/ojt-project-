"""PAYFLOW application configuration.

All paths are resolved dynamically so that tests can isolate persistence by
setting the PAYFLOW_DATA_DIR environment variable before importing the app.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    """Return the active data directory (overridable for tests)."""
    return Path(os.environ.get("PAYFLOW_DATA_DIR", str(PROJECT_ROOT / "data"))).resolve()


def secrets_dir() -> Path:
    d = data_dir() / ".secrets"
    d.mkdir(parents=True, exist_ok=True)
    return d


DATA_FILES: Dict[str, object] = {
    "users.json": [],
    "accounts.json": [],
    "entries.json": [],
    "balances.json": {},
    "wallets.json": [],
    "beneficiaries.json": [],
    "payment_requests.json": [],
    "merchants.json": [],
    "sessions.json": [],
    "notifications.json": [],
    "settings.json": [],
    "audit_logs.json": [],
    "security_events.json": [],
}

# Session policy
SESSION_COOKIE = "payflow_session"
SESSION_SLIDING_HOURS = 24
SESSION_ABSOLUTE_DAYS = 7

# Security policy
PASSWORD_MEMORY_COST_KIB = 65536
PASSWORD_TIME_COST = 3
PASSWORD_PARALLELISM = 1
PASSWORD_SALT_BYTES = 16
MAX_FAILED_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
MFA_STEP_UP_PAISE = 1_000_000          # Rs. 10,000
DEFAULT_DAILY_LIMIT_PAISE = 10_000_000  # Rs. 1,00,000

# Simulation constants
INR_PER_RUPEE = 100
SYSTEM_SETTLEMENT_ACCOUNT = "acc_sys_settlement"
SYSTEM_FEES_ACCOUNT = "acc_sys_fees"
SYSTEM_UTILITIES_ACCOUNT = "acc_sys_utilities"


def system_accounts() -> List[dict]:
    """System/chart-of-accounts skeleton provisioned on first boot."""
    return [
        {
            "id": SYSTEM_SETTLEMENT_ACCOUNT,
            "code": "SYS-SETTLEMENT",
            "name": "Platform Settlement Reserve",
            "account_type": "Asset",
            "role": "Settlement",
            "user_id": None,
            "allow_negative": True,
            "opening_balance_paise": 100_000_000_000,  # Rs. 100 crore funding pool
            "active": True,
        },
        {
            "id": SYSTEM_FEES_ACCOUNT,
            "code": "SYS-FEES",
            "name": "Platform Fee Clearing",
            "account_type": "Asset",
            "role": "Fees",
            "user_id": None,
            "allow_negative": True,
            "opening_balance_paise": 0,
            "active": True,
        },
        {
            "id": SYSTEM_UTILITIES_ACCOUNT,
            "code": "SYS-UTILITIES",
            "name": "Utility Biller Settlement",
            "account_type": "Asset",
            "role": "Utility",
            "user_id": None,
            "allow_negative": True,
            "opening_balance_paise": 0,
            "active": True,
        },
    ]


def utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
