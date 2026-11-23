"""Wallet provisioning, simulated funding and internal transfers."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..config import utc_now_iso
from ..core.json_store import stores
from ..core.security import new_id
from .audit_service import notify, record_audit
from .ledger_service import ledger, LedgerError


class WalletError(ValueError):
    pass


def _rupees(paise: int) -> str:
    return f"Rs. {paise / 100:,.2f}"


def list_wallets(user_id: str) -> List[Dict[str, Any]]:
    balances: Dict[str, int] = {}
    for account in ledger.get_accounts(user_id=user_id):
        balances[account["id"]] = account.get("balance_paise", 0)
    result = []
    for wallet in stores.wallets.read():
        if wallet.get("user_id") == user_id:
            row = dict(wallet)
            row["balance_paise"] = balances.get(wallet["account_id"], 0)
            result.append(row)
    return result


def get_wallet(wallet_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    for wallet in list_wallets(user_id) if user_id else stores.wallets.read():
        if wallet["id"] == wallet_id:
            return wallet
    return None


def primary_wallet(user_id: str) -> Dict[str, Any]:
    wallets = list_wallets(user_id)
    wallet = next((w for w in wallets if w.get("is_primary")), None)
    if not wallet:
        raise WalletError("No active primary wallet")
    return wallet


def create_wallet(user: Dict[str, Any], payload) -> Dict[str, Any]:
    data = payload.model_dump()
    code = data.get("code") or f"WLT-{user['username'][:5].upper()}-{new_id('x')[-4:].upper()}"
    account = ledger.create_account({
        "code": code,
        "name": data["label"],
        "account_type": "Asset",
        "role": "Wallet",
        "user_id": user["id"],
        "allow_negative": False,
        "opening_balance_paise": 0,
    })
    wallet = {
        "id": new_id("wlt"),
        "user_id": user["id"],
        "account_id": account["id"],
        "label": data["label"],
        "currency": "INR",
        "is_primary": False,
        "status": "ACTIVE",
        "created_at": utc_now_iso(),
    }
    stores.wallets.append(wallet)
    record_audit(user["id"], "WALLET_CREATED", account["id"], "SUCCESS", {"label": data["label"]})
    return {**wallet, "balance_paise": 0}


def top_up(user: Dict[str, Any], payload) -> Dict[str, Any]:
    data = payload.model_dump()
    wallet_id = data.get("wallet_id")
    wallet = get_wallet(wallet_id, user["id"]) if wallet_id else primary_wallet(user["id"])
    if not wallet:
        raise WalletError("Wallet not found")
    amount = int(data["amount_paise"])
    reference = data.get("reference") or f"TOPUP/{user['username'].upper()}/{new_id('r')[-12:]}"
    entry = ledger.top_up(
        wallet["account_id"], amount,
        description=f"Simulated top-up to {wallet['label']}",
        reference=reference,
        metadata={"user_id": user["id"], "wallet_id": wallet["id"], "payment_method": "SIMULATED"},
    )
    notify(user["id"], "Wallet topped up", f"{_rupees(amount)} added to {wallet['label']}.",
           "wallet", {"transaction_id": entry["transaction_id"]})
    record_audit(user["id"], "WALLET_TOPUP", wallet["id"], "SUCCESS",
                 {"amount_paise": amount, "transaction_id": entry["transaction_id"]})
    return {"wallet": get_wallet(wallet["id"], user["id"]), "entry": entry}


def internal_transfer(user: Dict[str, Any], payload) -> Dict[str, Any]:
    data = payload.model_dump()
    source = get_wallet(data["from_wallet_id"], user["id"])
    target = get_wallet(data["to_wallet_id"], user["id"])
    if not source or not target:
        raise WalletError("Source or destination wallet not found")
    amount = int(data["amount_paise"])
    fee = int(data.get("fee_paise", 0))
    entry = ledger.transfer(
        from_account_id=source["account_id"],
        to_account_id=target["account_id"],
        amount_paise=amount,
        description=data.get("description", "Wallet to wallet transfer"),
        category="Wallet Transfer",
        reference=f"WLTX/{new_id('r')[-10:]}",
        fee_paise=fee,
        metadata={"user_id": user["id"], "from_wallet_id": source["id"], "to_wallet_id": target["id"]},
    )
    notify(user["id"], "Wallet transfer complete",
           f"{_rupees(amount)} moved from {source['label']} to {target['label']}.",
           "wallet", {"transaction_id": entry["transaction_id"]})
    record_audit(user["id"], "WALLET_TRANSFER", source["id"], "SUCCESS",
                 {"amount_paise": amount, "fee_paise": fee})
    return {
        "entry": entry,
        "source": get_wallet(source["id"], user["id"]),
        "target": get_wallet(target["id"], user["id"]),
    }
