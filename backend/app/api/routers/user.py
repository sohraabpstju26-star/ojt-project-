"""Self-service endpoints: transactions, notifications, settings, cards, sessions."""
from __future__ import annotations

import hashlib
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from ...config import utc_now_iso
from ...core.json_store import stores
from ...services import auth_service
from ...services.ledger_service import ledger
from ..deps import get_current_user

router = APIRouter(prefix="/api", tags=["Self Service"])


def _user_accounts(user_id: str) -> set[str]:
    return {w["account_id"] for w in stores.wallets.read() if w.get("user_id") == user_id}


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
@router.get("/transactions")
def transactions(category: str | None = None, start_date: str | None = None,
                 end_date: str | None = None, user=Depends(get_current_user)):
    accounts = _user_accounts(user["id"])
    rows = ledger.get_transaction_history(None, category, start_date, end_date)
    result = []
    for entry in rows:
        if not any(l["account_id"] in accounts for l in entry["lines"]):
            continue
        meta = entry.get("metadata", {})
        direction = "NEUTRAL"
        amount = 0
        for line in entry["lines"]:
            if line["account_id"] in accounts:
                if line.get("credit_paise", 0) > 0:
                    direction = "DEBIT"
                    amount = line["credit_paise"]
                elif line.get("debit_paise", 0) > 0:
                    direction = "CREDIT"
                    amount = line["debit_paise"]
        result.append({
            "transaction_id": entry["transaction_id"],
            "reference": entry.get("reference"),
            "timestamp": entry["timestamp"],
            "date": entry["date"],
            "description": entry["description"],
            "category": entry["category"],
            "amount_paise": amount,
            "direction": direction,
            "counterparty": meta.get("receiver_vpa") or meta.get("sender_vpa") or "PAYFLOW",
            "status": "REVERSED" if entry.get("is_reversal") else "COMPLETED",
        })
    return result


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
@router.get("/notifications")
def notifications(user=Depends(get_current_user)):
    rows = [n for n in stores.notifications.read() if n.get("user_id") == user["id"]]
    return sorted(rows, key=lambda n: n.get("created_at", ""), reverse=True)


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: str, user=Depends(get_current_user)):
    def mutate(items):
        for note in items:
            if note["id"] == notification_id and note.get("user_id") == user["id"]:
                note["read"] = True
    stores.notifications.mutate(mutate)
    return {"status": "OK"}


@router.post("/notifications/read-all")
def mark_all_read(user=Depends(get_current_user)):
    def mutate(items):
        for note in items:
            if note.get("user_id") == user["id"]:
                note["read"] = True
    stores.notifications.mutate(mutate)
    return {"status": "OK"}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
@router.get("/settings")
def get_settings(user=Depends(get_current_user)):
    record = next((s for s in stores.settings.read() if s.get("user_id") == user["id"]), None)
    if not record:
        raise HTTPException(status_code=404, detail="Settings not found")
    return record


@router.put("/settings")
def update_settings(payload: Dict[str, Any], user=Depends(get_current_user)):
    allowed = {"theme", "currency_format", "daily_limit_paise", "notifications", "privacy"}
    result = {}

    def mutate(items):
        for s in items:
            if s.get("user_id") == user["id"]:
                for key, value in payload.items():
                    if key in allowed:
                        s[key] = value
                s["updated_at"] = utc_now_iso()
                result.update(s)
    stores.settings.mutate(mutate)
    if not result:
        raise HTTPException(status_code=404, detail="Settings not found")
    return result


# ---------------------------------------------------------------------------
# Simulated cards
# ---------------------------------------------------------------------------
def _cards(user: dict) -> list[dict]:
    digest = hashlib.sha256(user["id"].encode()).hexdigest()
    settings = next((s for s in stores.settings.read() if s.get("user_id") == user["id"]), {})
    frozen = settings.get("frozen_cards", [])
    cards = []
    for i in range(2):
        card_id = f"card_{user['id'][-6:]}_{i+1}"
        last4 = digest[i * 4:i * 4 + 4]
        cards.append({
            "id": card_id,
            "brand": "VISA" if i == 0 else "Mastercard",
            "holder": user["full_name"].upper(),
            "masked_number": f"•••• •••• •••• {last4}",
            "last4": last4,
            "expiry": "12/29",
            "frozen": card_id in frozen,
            "status": "FROZEN" if card_id in frozen else "ACTIVE",
            "network": "SIMULATED - NOT A REAL CARD",
        })
    return cards


@router.get("/cards")
def list_cards(user=Depends(get_current_user)):
    return _cards(user)


@router.post("/cards/{card_id}/freeze")
def toggle_freeze(card_id: str, user=Depends(get_current_user)):
    def mutate(items):
        for s in items:
            if s.get("user_id") == user["id"]:
                frozen = s.setdefault("frozen_cards", [])
                if card_id in frozen:
                    frozen.remove(card_id)
                else:
                    frozen.append(card_id)
    stores.settings.mutate(mutate)
    return next(c for c in _cards(user) if c["id"] == card_id)


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------
@router.get("/security/sessions")
def list_sessions(user=Depends(get_current_user)):
    return auth_service.active_sessions(user["id"])


@router.delete("/security/sessions/{token_hash}")
def revoke_session(token_hash: str, user=Depends(get_current_user)):
    auth_service.revoke_session(user["id"], token_hash)
    return {"status": "REVOKED"}
