"""Saved beneficiaries / favourites with duplicate validation."""
from __future__ import annotations

from typing import Any, Dict, List

from ..config import utc_now_iso
from ..core.json_store import stores
from ..core.security import new_id
from .audit_service import record_audit
from .payment_service import PaymentError, resolve_recipient


class BeneficiaryError(ValueError):
    pass


def list_beneficiaries(user_id: str) -> List[Dict[str, Any]]:
    rows = [b for b in stores.beneficiaries.read() if b.get("user_id") == user_id]
    rows.sort(key=lambda b: (not b.get("favorite", False), b.get("nickname", "")))
    return rows


def add_beneficiary(user: Dict[str, Any], payload) -> Dict[str, Any]:
    data = payload.model_dump()
    target = resolve_recipient(data["identifier"], user["id"])
    existing = [b for b in stores.beneficiaries.read() if b.get("user_id") == user["id"]]
    if any(b["beneficiary_user_id"] == target["user_id"] for b in existing):
        raise BeneficiaryError("Beneficiary already saved")
    beneficiary = {
        "id": new_id("ben"),
        "user_id": user["id"],
        "beneficiary_user_id": target["user_id"],
        "vpa": target["vpa"],
        "nickname": data["nickname"],
        "category": data.get("category", "P2P"),
        "favorite": bool(data.get("favorite", False)),
        "created_at": utc_now_iso(),
    }
    stores.beneficiaries.append(beneficiary)
    record_audit(user["id"], "BENEFICIARY_ADDED", target["user_id"], "SUCCESS")
    return beneficiary


def update_beneficiary(user: Dict[str, Any], beneficiary_id: str, payload) -> Dict[str, Any]:
    data = payload.model_dump(exclude_none=True)
    result = {}

    def mutate(items):
        for b in items:
            if b["id"] == beneficiary_id and b.get("user_id") == user["id"]:
                b.update(data)
                result.update(b)
    stores.beneficiaries.mutate(mutate)
    if not result:
        raise BeneficiaryError("Beneficiary not found")
    return result


def delete_beneficiary(user: Dict[str, Any], beneficiary_id: str) -> None:
    def mutate(items):
        items[:] = [b for b in items if not (b["id"] == beneficiary_id and b.get("user_id") == user["id"])]
    stores.beneficiaries.mutate(mutate)
    record_audit(user["id"], "BENEFICIARY_DELETED", beneficiary_id, "SUCCESS")


def toggle_favorite(user: Dict[str, Any], beneficiary_id: str) -> Dict[str, Any]:
    result = {}

    def mutate(items):
        for b in items:
            if b["id"] == beneficiary_id and b.get("user_id") == user["id"]:
                b["favorite"] = not b.get("favorite", False)
                result.update(b)
    stores.beneficiaries.mutate(mutate)
    if not result:
        raise BeneficiaryError("Beneficiary not found")
    return result


def beneficiary_history(user_id: str, beneficiary_id: str) -> List[Dict[str, Any]]:
    beneficiary = next((b for b in stores.beneficiaries.read()
                        if b["id"] == beneficiary_id and b.get("user_id") == user_id), None)
    if not beneficiary:
        raise BeneficiaryError("Beneficiary not found")
    from .ledger_service import ledger
    entries = ledger.get_transaction_history()
    counterparty_accounts = {w["account_id"] for w in stores.wallets.read()
                             if w.get("user_id") == beneficiary["beneficiary_user_id"]}
    return [e for e in entries if any(l["account_id"] in counterparty_accounts for l in e.get("lines", []))]
