"""P2P payments, VPA resolution, QR generation and Scan & Pay simulation."""
from __future__ import annotations

import io
import urllib.parse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

import qrcode
from qrcode.image.svg import SvgPathImage

from .. import config
from ..core.json_store import stores
from ..core.security import new_id
from ..config import utc_now_iso
from .audit_service import notify, record_audit, record_security_event
from .auth_service import StepUpRequired, assert_step_up
from .ledger_service import ledger, LedgerError
from . import wallet_service


class PaymentError(ValueError):
    pass


def _rupees(paise: int) -> str:
    return f"Rs. {paise / 100:,.2f}"


def rupees_to_paise(value: str) -> int:
    """Convert a rupee string to integer paise without any float arithmetic."""
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise PaymentError("Invalid monetary amount")
    if amount < 0 or amount != amount.quantize(Decimal("0.01")):
        raise PaymentError("Amount must have at most two decimal places")
    return int(amount * 100)


def paise_to_rupees_str(paise: int) -> str:
    """Exact integer-paise to 'rupees.paise' string for QR payloads."""
    return f"{paise // 100}.{paise % 100:02d}"


def _primary_account(user_id: str) -> str:
    return wallet_service.primary_wallet(user_id)["account_id"]


def resolve_recipient(identifier: str, sender_id: Optional[str] = None) -> Dict[str, Any]:
    """Resolve a VPA, phone number, username, or saved beneficiary id."""
    identifier = identifier.strip()
    users = stores.users.read()

    beneficiary = next((b for b in stores.beneficiaries.read()
                        if b["id"] == identifier and (sender_id is None or b["user_id"] == sender_id)), None)
    if beneficiary:
        target_id = beneficiary["beneficiary_user_id"]
    else:
        low = identifier.lower()
        user = next((u for u in users if u["vpa"].lower() == low or u["phone"] == identifier
                     or u["username"].lower() == low or u["email"].lower() == low), None)
        if not user:
            raise PaymentError(f"Recipient not found: {identifier}")
        target_id = user["id"]

    user = next((u for u in users if u["id"] == target_id), None)
    if not user:
        raise PaymentError("Recipient identity could not be resolved")
    if sender_id and user["id"] == sender_id:
        raise PaymentError("Cannot pay yourself")
    if not user.get("is_active", True):
        raise PaymentError("Recipient account is inactive")
    return {
        "user_id": user["id"],
        "vpa": user["vpa"],
        "name": user["full_name"],
        "full_name": user["full_name"],
        "username": user["username"],
        "account_id": _primary_account(user["id"]),
        "role": user["role"],
    }


def _daily_spend(user_id: str, account_ids: set[str]) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    total = 0
    for entry in stores.entries.read():
        if entry.get("date") != today:
            continue
        if entry.get("category") in ("Top-up", "Refund", "Reversal"):
            continue
        for line in entry.get("lines", []):
            if line["account_id"] in account_ids:
                total += int(line.get("credit_paise", 0))
    return total


def check_wallet_funds(wallet: Dict[str, Any], amount: int) -> None:
    """Pre-flight funds check so balance errors surface before MFA step-up."""
    available = ledger.balance(wallet["account_id"])
    if available < amount:
        raise PaymentError(
            f"Insufficient balance in {wallet.get('label', 'wallet')}: "
            f"have {_rupees(available)}, need {_rupees(amount)}"
        )


def _check_limit(user: Dict[str, Any], amount: int) -> None:
    settings = next((s for s in stores.settings.read() if s.get("user_id") == user["id"]), {})
    limit = int(settings.get("daily_limit_paise", config.DEFAULT_DAILY_LIMIT_PAISE))
    account_ids = {w["account_id"] for w in wallet_service.list_wallets(user["id"])}
    spent = _daily_spend(user["id"], account_ids)
    if spent + amount > limit:
        raise PaymentError(
            f"Daily transaction limit exceeded (spent {_rupees(spent)}, limit {_rupees(limit)})"
        )


def qr_payload(user: Dict[str, Any], amount_paise: Optional[int] = None, note: Optional[str] = None) -> str:
    params = {"pa": user["vpa"], "pn": user["full_name"], "cu": "INR"}
    if amount_paise:
        params["am"] = paise_to_rupees_str(amount_paise)
    if note:
        params["tn"] = note
    return "payflow://pay?" + urllib.parse.urlencode(params)


def qr_payload_to_svg(payload: str) -> str:
    """Render a high-contrast QR as inline SVG (backend-generated, injected by UI)."""
    image = qrcode.make(payload, image_factory=SvgPathImage, box_size=8, border=2)
    buffer = io.BytesIO()
    image.save(buffer)
    svg = buffer.getvalue().decode("utf-8")
    # Embed the raw payload so uploaded SVG scans can be decoded by the UI.
    desc = f"<desc>{__import__('html').escape(payload)}</desc>"
    if "<svg" in svg:
        end = svg.index(">") + 1
        svg = svg[:end] + desc + svg[end:]
    return svg


def parse_qr_payload(payload: str) -> Dict[str, str]:
    payload = payload.strip()
    if not payload.startswith("payflow://pay?"):
        raise PaymentError("Invalid PAYFLOW QR payload (expected payflow://pay?...)")
    query = payload.split("?", 1)[1]
    params = urllib.parse.parse_qs(query, keep_blank_values=True)
    required = ("pa", "pn", "cu")
    for key in required:
        if key not in params or not params[key][0]:
            raise PaymentError(f"QR payload missing required parameter: {key}")
    if params["cu"][0] != "INR":
        raise PaymentError("Unsupported QR currency")
    return {k: v[0] for k, v in params.items()}


def send_money(user: Dict[str, Any], session: Dict[str, Any], payload, ip: Optional[str] = None) -> Dict[str, Any]:
    data = payload.model_dump()
    recipient = resolve_recipient(data["recipient"], user["id"])
    amount = int(data["amount_paise"])
    fee = int(data.get("fee_paise", 0))
    wallet_id = data.get("from_wallet_id")
    wallet = wallet_service.get_wallet(wallet_id, user["id"]) if wallet_id else wallet_service.primary_wallet(user["id"])
    if not wallet:
        raise PaymentError("Source wallet not found")
    check_wallet_funds(wallet, amount + fee)
    _check_limit(user, amount + fee)
    assert_step_up(session, amount + fee, data.get("totp_code"), user)
    reference = f"UPI/{datetime.now(timezone.utc).strftime('%Y%m%d')}/{new_id('r')[-12:]}"
    entry = ledger.transfer(
        from_account_id=wallet["account_id"],
        to_account_id=recipient["account_id"],
        amount_paise=amount,
        description=f"Payment to {recipient['vpa']} for {data.get('note', 'Payment')}",
        category="P2P Transfer",
        reference=reference,
        fee_paise=fee,
        metadata={
            "sender_vpa": user["vpa"], "receiver_vpa": recipient["vpa"],
            "payment_method": "VPA", "fee_paise": fee, "note": data.get("note", "Payment"),
            "sender_user_id": user["id"], "receiver_user_id": recipient["user_id"],
        },
    )
    notify(recipient["user_id"], "Money received", f"{_rupees(amount)} from {user['full_name']}",
           "payment", {"transaction_id": entry["transaction_id"]})
    notify(user["id"], "Payment sent", f"{_rupees(amount)} to {recipient['full_name']}",
           "payment", {"transaction_id": entry["transaction_id"]})
    record_audit(user["id"], "P2P_SEND", recipient["user_id"], "SUCCESS",
                 {"amount_paise": amount, "transaction_id": entry["transaction_id"]}, ip=ip)
    return {
        "entry": entry,
        "recipient": recipient,
        "receipt": receipt_for(entry["transaction_id"], user["id"]),
    }


def scan_pay(user: Dict[str, Any], session: Dict[str, Any], payload, ip: Optional[str] = None) -> Dict[str, Any]:
    data = payload.model_dump()
    parsed = parse_qr_payload(data["payload"])
    merchant = next((m for m in stores.merchants.read() if m["vpa"].lower() == parsed["pa"].lower()), None)
    if not merchant:
        # Allow paying any registered VPA, but mark verification accordingly.
        recipient = resolve_recipient(parsed["pa"], user["id"])
        merchant = {
            "vpa": recipient["vpa"], "name": recipient["name"],
            "category": "P2P", "account_id": recipient["account_id"],
            "verified": False, "user_id": recipient["user_id"],
        }
    if "am" in parsed:
        amount = rupees_to_paise(parsed["am"])
        if amount <= 0:
            raise PaymentError("QR amount must be positive")
    else:
        raise PaymentError("QR payload does not include an amount (am)")
    note = parsed.get("tn", "QR checkout")
    wallet_id = data.get("from_wallet_id")
    wallet = wallet_service.get_wallet(wallet_id, user["id"]) if wallet_id else wallet_service.primary_wallet(user["id"])
    if not wallet:
        raise PaymentError("Source wallet not found")
    check_wallet_funds(wallet, amount)
    _check_limit(user, amount)
    assert_step_up(session, amount, data.get("totp_code"), user)
    reference = f"UPI/QR/{datetime.now(timezone.utc).strftime('%Y%m%d')}/{new_id('r')[-12:]}"
    entry = ledger.transfer(
        from_account_id=wallet["account_id"],
        to_account_id=merchant["account_id"],
        amount_paise=amount,
        description=f"QR payment to {merchant['name']} for {note}",
        category="Merchant Payment",
        reference=reference,
        metadata={
            "sender_vpa": user["vpa"], "receiver_vpa": merchant["vpa"],
            "payment_method": "QR", "fee_paise": 0, "note": note,
            "merchant_verified": merchant.get("verified", False),
            "merchant_category": merchant.get("category", "P2P"),
            "sender_user_id": user["id"], "receiver_user_id": merchant.get("user_id"),
        },
    )
    if merchant.get("user_id"):
        notify(merchant["user_id"], "Merchant payment received",
               f"{_rupees(amount)} via QR from {user['full_name']}",
               "payment", {"transaction_id": entry["transaction_id"]})
    notify(user["id"], "QR payment complete", f"{_rupees(amount)} paid to {merchant['name']}",
           "payment", {"transaction_id": entry["transaction_id"]})
    record_audit(user["id"], "SCAN_PAY", merchant["vpa"], "SUCCESS",
                 {"amount_paise": amount, "transaction_id": entry["transaction_id"]}, ip=ip)
    return {"entry": entry, "merchant": merchant, "receipt": receipt_for(entry["transaction_id"], user["id"])}


def receipt_for(transaction_id: str, viewer_user_id: Optional[str] = None) -> Dict[str, Any]:
    entry = ledger.get_entry(transaction_id)
    if not entry:
        raise PaymentError(f"Transaction not found: {transaction_id}")
    accounts = {a["id"]: a for a in stores.accounts.read()}
    users = {u["id"]: u for u in stores.users.read()}
    wallet_accounts = {w["account_id"]: w for w in stores.wallets.read()}

    viewer_accounts = set()
    if viewer_user_id:
        viewer_accounts = {w["account_id"] for w in wallet_service.list_wallets(viewer_user_id)}

    direction = "NEUTRAL"
    for line in entry.get("lines", []):
        if line["account_id"] in viewer_accounts:
            if line.get("credit_paise", 0) > 0:
                direction = "DEBIT"
            elif line.get("debit_paise", 0) > 0:
                direction = "CREDIT"

    counterparty = "PLATFORM"
    metadata = entry.get("metadata", {})
    if viewer_user_id:
        if direction == "DEBIT":
            counterparty = metadata.get("receiver_vpa") or "Recipient"
        elif direction == "CREDIT":
            counterparty = metadata.get("sender_vpa") or "Sender"
    if counterparty == "PLATFORM":
        counterparty = metadata.get("receiver_vpa") or metadata.get("sender_vpa") or "PAYFLOW"

    return {
        "transaction_id": entry["transaction_id"],
        "reference": entry.get("reference") or "",
        "date": entry["date"],
        "timestamp": entry["timestamp"],
        "description": entry["description"],
        "category": entry["category"],
        "amount_paise": entry["total_paise"] - int(metadata.get("fee_paise", 0)),
        "fee_paise": int(metadata.get("fee_paise", 0)),
        "total_paise": entry["total_paise"],
        "direction": direction,
        "counterparty": counterparty,
        "status": "REVERSED" if entry.get("is_reversal") else "COMPLETED",
        "lines": entry.get("lines", []),
        "metadata": metadata,
    }


def receipt_html(receipt: Dict[str, Any]) -> str:
    def inr(p): return f"Rs. {p / 100:,.2f}"
    rows = "".join(
        f"<tr><td>{l['account_id']}</td><td>{inr(l.get('debit_paise',0))}</td>"
        f"<td>{inr(l.get('credit_paise',0))}</td></tr>"
        for l in receipt["lines"]
    )
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>PAYFLOW Receipt</title>
<style>body{{font-family:Inter,Arial,sans-serif;background:#000000;color:#f8fafc;padding:32px}}
.card{{background:#101114;border:1px solid #23252b;border-radius:14px;padding:28px;max-width:640px;margin:auto}}
h1{{color:#3b82f6}} table{{width:100%;border-collapse:collapse;margin-top:16px}}
td,th{{padding:8px;border-bottom:1px solid #23252b;text-align:left;font-size:13px}}
.ok{{color:#10b981}}</style></head><body><div class='card'>
<h1>PAYFLOW · Digital Receipt</h1><p class='ok'>● {receipt['status']}</p>
<p><b>Transaction ID</b>: {receipt['transaction_id']}<br><b>Reference</b>: {receipt['reference']}<br>
<b>Date</b>: {receipt['timestamp']}<br><b>Counterparty</b>: {receipt['counterparty']}<br>
<b>Description</b>: {receipt['description']}</p>
<h2>{inr(receipt['total_paise'])}</h2>
<table><tr><th>Account</th><th>Debit</th><th>Credit</th></tr>{rows}</table>
<p style='color:#64748b;font-size:11px;margin-top:20px'>Simulated environment. Not a real banking instrument.</p>
</div></body></html>"""
