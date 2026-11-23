"""Pull-based 'Collect' payment requests with explicit approval state machine."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from ..config import utc_now_iso
from ..core.json_store import stores
from ..core.security import new_id
from .audit_service import notify, record_audit
from .auth_service import assert_step_up
from .ledger_service import ledger
from .payment_service import PaymentError, check_wallet_funds, resolve_recipient
from . import wallet_service


class RequestError(ValueError):
    pass


def _expire_stale() -> None:
    now = datetime.now(timezone.utc)

    def mutate(items):
        for r in items:
            if r.get("status") == "PENDING":
                expiry = datetime.fromisoformat(r["expires_at"].replace("Z", "+00:00"))
                if expiry < now:
                    r["status"] = "EXPIRED"
                    r["updated_at"] = utc_now_iso()
    stores.requests.mutate(mutate)


def _out(r: Dict[str, Any], viewer_id: str) -> Dict[str, Any]:
    direction = "OUTGOING" if r["creator_user_id"] == viewer_id else "INCOMING"
    return {**{k: v for k, v in r.items() if k != "_id"}, "direction": direction}


def list_requests(user_id: str) -> List[Dict[str, Any]]:
    _expire_stale()
    rows = [r for r in stores.requests.read()
            if r.get("creator_user_id") == user_id or r.get("payer_user_id") == user_id]
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return [_out(r, user_id) for r in rows]


def create_request(user: Dict[str, Any], payload) -> Dict[str, Any]:
    data = payload.model_dump()
    payer = resolve_recipient(data["payer"], user["id"])
    now = datetime.now(timezone.utc)
    request = {
        "id": new_id("req"),
        "creator_user_id": user["id"],
        "creator_vpa": user["vpa"],
        "payer_user_id": payer["user_id"],
        "payer_vpa": payer["vpa"],
        "amount_paise": int(data["amount_paise"]),
        "note": data.get("note", "Payment request"),
        "status": "PENDING",
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "expires_at": (now + timedelta(hours=24)).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "transaction_id": None,
        "from_wallet_id": data.get("from_wallet_id"),
    }
    stores.requests.append(request)
    notify(payer["user_id"], "Payment request received",
           f"{user['full_name']} requested Rs. {request['amount_paise']/100:,.2f}",
           "request", {"request_id": request["id"]})
    record_audit(user["id"], "REQUEST_CREATED", payer["user_id"], "SUCCESS",
                 {"request_id": request["id"], "amount_paise": request["amount_paise"]})
    return _out(request, user["id"])


def _get(request_id: str) -> Dict[str, Any]:
    row = next((r for r in stores.requests.read() if r["id"] == request_id), None)
    if not row:
        raise RequestError("Payment request not found")
    return row


def _mutate_status(request_id: str, status: str, **extra) -> Dict[str, Any]:
    result = {}

    def mutate(items):
        for r in items:
            if r["id"] == request_id:
                r["status"] = status
                r["updated_at"] = utc_now_iso()
                r.update(extra)
                result.update(r)
    stores.requests.mutate(mutate)
    return result


def approve_request(request_id: str, payer: Dict[str, Any], session: Dict[str, Any],
                    approve_in=None) -> Dict[str, Any]:
    _expire_stale()
    request = _get(request_id)
    if request.get("payer_user_id") != payer["id"]:
        raise RequestError("Only the designated payer may approve this request")
    if request["status"] != "PENDING":
        raise RequestError(f"Request is {request['status']}, not PENDING")
    totp = approve_in.totp_code if approve_in else None
    wallet_id = approve_in.from_wallet_id if approve_in else None

    wallet = (wallet_service.get_wallet(wallet_id, payer["id"]) if wallet_id
              else wallet_service.primary_wallet(payer["id"]))
    check_wallet_funds(wallet, request["amount_paise"])
    assert_step_up(session, request["amount_paise"], totp, payer)
    creator_wallet = wallet_service.primary_wallet(request["creator_user_id"])
    entry = ledger.transfer(
        from_account_id=wallet["account_id"],
        to_account_id=creator_wallet["account_id"],
        amount_paise=request["amount_paise"],
        description=f"Approved collect request: {request['note']}",
        category="P2P Transfer",
        reference=f"COLLECT/{request['id'][-8:]}",
        metadata={
            "sender_vpa": payer["vpa"], "receiver_vpa": request["creator_vpa"],
            "payment_method": "COLLECT", "fee_paise": 0,
            "request_id": request_id,
        },
    )
    updated = _mutate_status(request_id, "APPROVED", transaction_id=entry["transaction_id"])
    notify(request["creator_user_id"], "Request approved",
           f"{payer['full_name']} paid Rs. {request['amount_paise']/100:,.2f}",
           "request", {"request_id": request_id, "transaction_id": entry["transaction_id"]})
    record_audit(payer["id"], "REQUEST_APPROVED", request_id, "SUCCESS",
                 {"transaction_id": entry["transaction_id"]})
    return {**_out(updated, payer["id"]), "entry": entry}


def reject_request(request_id: str, payer: Dict[str, Any]) -> Dict[str, Any]:
    request = _get(request_id)
    if request.get("payer_user_id") != payer["id"]:
        raise RequestError("Only the designated payer may reject this request")
    if request["status"] != "PENDING":
        raise RequestError("Only pending requests can be rejected")
    updated = _mutate_status(request_id, "REJECTED")
    notify(request["creator_user_id"], "Request rejected",
           f"{payer['full_name']} declined your payment request", "request", {"request_id": request_id})
    record_audit(payer["id"], "REQUEST_REJECTED", request_id, "SUCCESS")
    return _out(updated, payer["id"])


def cancel_request(request_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    request = _get(request_id)
    if request.get("creator_user_id") != user["id"]:
        raise RequestError("Only the creator may cancel this request")
    if request["status"] != "PENDING":
        raise RequestError("Only pending requests can be cancelled")
    updated = _mutate_status(request_id, "CANCELLED")
    record_audit(user["id"], "REQUEST_CANCELLED", request_id, "SUCCESS")
    return _out(updated, user["id"])
