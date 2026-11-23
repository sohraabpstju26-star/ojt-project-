"""Idempotent first-boot provisioning of system accounts and demo identities."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List

from .. import config
from ..core.json_store import stores
from ..core.security import hash_password, new_id
from ..services.ledger_service import ledger


DEMO_USERS = [
    {"username": "admin", "full_name": "PAYFLOW Administrator", "email": "admin@payflow.local",
     "phone": "+910000000001", "password": "Admin@12345", "role": "Administrator", "vpa": "admin@payflow"},
    {"username": "auditor", "full_name": "Priya Auditor", "email": "auditor@payflow.local",
     "phone": "+910000000002", "password": "Audit@12345", "role": "Auditor", "vpa": "auditor@payflow"},
    {"username": "operator", "full_name": "Rohan Operator", "email": "operator@payflow.local",
     "phone": "+910000000003", "password": "Oper@12345", "role": "Operator", "vpa": "operator@payflow"},
    {"username": "aditi_sharma", "full_name": "Aditi Sharma", "email": "aditi@example.com",
     "phone": "+919876543210", "password": "Customer@123", "role": "Customer", "vpa": "aditi_sharma@payflow"},
    {"username": "rohit_kumar", "full_name": "Rohit Kumar", "email": "rohit@example.com",
     "phone": "+919876543211", "password": "Customer@123", "role": "Customer", "vpa": "rohit_kumar@payflow"},
    {"username": "starbucks", "full_name": "Starbucks Coffee India", "email": "starbucks@payflow.local",
     "phone": "+910000000010", "password": "Merchant@123", "role": "Merchant", "vpa": "starbucks@payflow"},
    {"username": "blue_tokai", "full_name": "Blue Tokai Coffee", "email": "bluetokai@payflow.local",
     "phone": "+910000000011", "password": "Merchant@123", "role": "Merchant", "vpa": "blue_tokai@payflow"},
    {"username": "reliance_fresh", "full_name": "Reliance Fresh", "email": "reliance@payflow.local",
     "phone": "+910000000012", "password": "Merchant@123", "role": "Merchant", "vpa": "reliance_fresh@payflow"},
    {"username": "metro_rail", "full_name": "Metro Rail Transit", "email": "metro@payflow.local",
     "phone": "+910000000013", "password": "Merchant@123", "role": "Merchant", "vpa": "metro_rail@payflow"},
]

MERCHANT_META = {
    "starbucks@payflow": ("Food & Beverage", "Coffee, tea and bakery"),
    "blue_tokai@payflow": ("Food & Beverage", "Speciality coffee roasters"),
    "reliance_fresh@payflow": ("Grocery", "Fresh produce and groceries"),
    "metro_rail@payflow": ("Travel", "Urban metro transit tickets"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ensure_initialized(force: bool = False) -> None:
    """Create all data files and seed demo data. Safe to call repeatedly."""
    data = config.data_dir()
    data.mkdir(parents=True, exist_ok=True)
    config.secrets_dir()

    for filename, default in config.DATA_FILES.items():
        path = data / filename
        if force or not path.exists():
            from ..core.json_store import JSONStore
            JSONStore(filename, default).write(default)

    if stores.accounts.read() == []:
        for account in config.system_accounts():
            ledger.create_account_with_id(account)

    users = stores.users.read()
    existing = {u["username"] for u in users}
    for spec in DEMO_USERS:
        if spec["username"] in existing:
            continue
        uid = new_id("usr")
        stamp = _now()
        user = {
            "id": uid,
            "username": spec["username"],
            "email": spec["email"],
            "phone": spec["phone"],
            "full_name": spec["full_name"],
            "role": spec["role"],
            "password_hash": hash_password(spec["password"]),
            "mfa_enabled": False,
            "mfa_secret_encrypted": None,
            "recovery_codes_encrypted": [],
            "vpa": spec["vpa"],
            "is_active": True,
            "failed_login_attempts": 0,
            "locked_until": None,
            "created_at": stamp,
            "updated_at": stamp,
        }
        users.append(user)

        account_id = f"acc_usr_{uid}_wallet"
        ledger.create_account_with_id(
            {
                "id": account_id,
                "code": f"WLT-{spec['username'][:6].upper()}-{uid[-4:].upper()}",
                "name": f"{spec['full_name']} Primary Wallet",
                "account_type": "Asset",
                "role": "Wallet",
                "user_id": uid,
                "allow_negative": False,
                "opening_balance_paise": 0,
                "active": True,
                "created_at": stamp,
            }
        )
        stores.wallets.append(
            {
                "id": new_id("wlt"),
                "user_id": uid,
                "account_id": account_id,
                "label": "Primary Wallet",
                "currency": "INR",
                "is_primary": True,
                "status": "ACTIVE",
                "created_at": stamp,
            }
        )
        stores.settings.append(
            {
                "user_id": uid,
                "theme": "dark",
                "currency_format": "INR",
                "daily_limit_paise": config.DEFAULT_DAILY_LIMIT_PAISE,
                "notifications": {"payments": True, "security": True, "product": False},
                "privacy": {"show_balance": True, "activity_visibility": "contacts"},
                "updated_at": stamp,
            }
        )
        stores.notifications.append(
            {
                "id": new_id("ntf"), "user_id": uid, "type": "system",
                "title": "Welcome to PAYFLOW",
                "message": "Your simulated wallet is ready. Never share your VPA PIN or credentials.",
                "read": False, "created_at": stamp,
            }
        )
    stores.users.write(users)

    merchants = stores.merchants.read()
    for vpa, (category, description) in MERCHANT_META.items():
        if any(m["vpa"] == vpa for m in merchants):
            continue
        user = next((u for u in stores.users.read() if u["vpa"] == vpa), None)
        if not user:
            continue
        merchants.append(
            {
                "id": new_id("mch"),
                "user_id": user["id"],
                "vpa": vpa,
                "name": user["full_name"],
                "category": category,
                "description": description,
                "verified": True,
                "account_id": f"acc_usr_{user['id']}_wallet",
                "created_at": _now(),
            }
        )
    stores.merchants.write(merchants)

    # Fund demo wallets and create a realistic transaction history.
    users_by_name = {u["username"]: u for u in stores.users.read()}
    wallets = stores.wallets.read()
    def primary_account(username: str) -> str:
        uid = users_by_name[username]["id"]
        return next(w["account_id"] for w in wallets if w["user_id"] == uid and w["is_primary"])

    if not [e for e in stores.entries.read() if e.get("metadata", {}).get("seed")]:
        funding = {"aditi_sharma": 5_000_000, "rohit_kumar": 2_500_000, "starbucks": 1_000_000}
        for username, amount in funding.items():
            ledger.top_up(
                primary_account(username), amount,
                description=f"Simulated wallet funding - {username}",
                reference=f"SEED/TOP/{username.upper()}",
                metadata={"seed": True},
            )
        seed_history(primary_account)


def seed_history(primary_account) -> None:
    """Backdated merchant/P2P activity so analytics has six months of signal."""
    specs = [
        (0, "aditi_sharma", "starbucks", 35_000, "Merchant Payment", "Coffee and croissant"),
        (5, "aditi_sharma", "blue_tokai", 48_000, "Merchant Payment", "Flat white"),
        (12, "aditi_sharma", "reliance_fresh", 245_000, "Merchant Payment", "Weekly groceries"),
        (28, "rohit_kumar", "aditi_sharma", 150_000, "P2P Transfer", "Dinner split"),
        (45, "aditi_sharma", "metro_rail", 6_000, "Merchant Payment", "Metro card recharge"),
        (70, "aditi_sharma", "starbucks", 28_000, "Merchant Payment", "Cafe latte"),
        (110, "rohit_kumar", "starbucks", 22_000, "Merchant Payment", "Espresso"),
        (150, "aditi_sharma", "rohit_kumar", 75_000, "P2P Transfer", "Concert tickets"),
    ]
    for days, sender, receiver, amount, category, note in specs:
        stamp = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
        from_acc, to_acc = primary_account(sender), primary_account(receiver)
        lines = [
            {"account_id": to_acc, "debit_paise": amount, "credit_paise": 0,
             "description": note},
            {"account_id": from_acc, "debit_paise": 0, "credit_paise": amount,
             "description": note},
        ]
        ledger.post_entry(
            description=f"{note} - {receiver}", lines=lines, category=category,
            reference=f"SEED/HIST/{days}/{sender[:3]}/{receiver[:3]}",
            metadata={
                "seed": True,
                "sender_vpa": f"{sender}@payflow" if "@" not in sender else sender,
                "receiver_vpa": f"{receiver}@payflow" if "@" not in receiver else receiver,
                "payment_method": "VPA", "fee_paise": 0,
            },
            occurred_at=stamp,
        )
