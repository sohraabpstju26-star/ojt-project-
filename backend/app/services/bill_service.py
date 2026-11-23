"""Simulated utility billers and recharges - no external integrations."""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, timedelta
from typing import Any, Dict, List

from ..config import SYSTEM_UTILITIES_ACCOUNT
from .audit_service import notify, record_audit
from .auth_service import assert_step_up
from .ledger_service import ledger
from .payment_service import check_wallet_funds
from . import wallet_service


class BillError(ValueError):
    pass


CATEGORIES: List[Dict[str, Any]] = [
    {"id": "mobile", "name": "Mobile Recharge", "icon": "phone",
     "providers": ["Airtel", "Jio", "Vi"]},
    {"id": "dth", "name": "DTH Television", "icon": "tv",
     "providers": ["Tata Play", "Airtel Digital TV", "Dish TV"]},
    {"id": "electricity", "name": "Electricity Bill", "icon": "bolt",
     "providers": ["BESCOM", "TSEDCL", "MSEDCL"]},
    {"id": "gas", "name": "Piped Gas", "icon": "flame",
     "providers": ["Indraprastha Gas", "Mahanagar Gas", "Gujarat Gas"]},
    {"id": "water", "name": "Water Utility", "icon": "drop",
     "providers": ["Delhi Jal Board", "BWSSB", "LMC Water"]},
    {"id": "broadband", "name": "Broadband / Fiber", "icon": "wifi",
     "providers": ["Airtel Fiber", "Jio Fiber", "Act Fibernet"]},
    {"id": "fastag", "name": "FASTag Toll Recharge", "icon": "car",
     "providers": ["NHAI FASTag", "Paytm FASTag", "HDFC FASTag"]},
    {"id": "property_tax", "name": "Municipal Property Tax", "icon": "building",
     "providers": ["MCD", "BBMP", "PMC"]},
]


def categories() -> List[Dict[str, Any]]:
    return CATEGORIES


def _encode_bill(data: Dict[str, Any]) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_bill(bill_id: str) -> Dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(bill_id.encode())
        data = json.loads(raw)
        if not all(k in data for k in ("category", "provider", "consumer_id", "amount_paise")):
            raise ValueError
        return data
    except Exception:
        raise BillError("Invalid or tampered bill reference")


def fetch_bill(payload) -> Dict[str, Any]:
    data = payload.model_dump()
    category = next((c for c in CATEGORIES if c["id"] == data["category"]), None)
    if not category:
        raise BillError("Unknown bill category")
    if data["provider"] not in category["providers"]:
        raise BillError("Provider not valid for this category")
    consumer = data["consumer_id"].strip()
    if len(consumer) < 3:
        raise BillError("Consumer ID is too short")

    seed = f"{data['category']}|{data['provider']}|{consumer}".encode()
    digest = hashlib.sha256(seed).digest()
    amount = 19_900 + int.from_bytes(digest[:4], "big") % 480_000
    due = date.today() + timedelta(days=7 + digest[4] % 14)
    bill = {
        "category": data["category"],
        "category_name": category["name"],
        "provider": data["provider"],
        "consumer_id": consumer,
        "amount_paise": amount,
        "due_date": due.isoformat(),
        "biller_reference": "BILL" + digest[8:16].hex().upper(),
        "status": "PENDING",
    }
    bill["bill_id"] = _encode_bill(bill)
    return bill


def pay_bill(user: Dict[str, Any], session: Dict[str, Any], payload) -> Dict[str, Any]:
    data = payload.model_dump()
    bill = _decode_bill(data["bill_id"])
    amount = int(bill["amount_paise"])

    wallet_id = data.get("from_wallet_id")
    wallet = (wallet_service.get_wallet(wallet_id, user["id"]) if wallet_id
              else wallet_service.primary_wallet(user["id"]))
    check_wallet_funds(wallet, amount)
    assert_step_up(session, amount, data.get("totp_code"), user)
    entry = ledger.transfer(
        from_account_id=wallet["account_id"],
        to_account_id=SYSTEM_UTILITIES_ACCOUNT,
        amount_paise=amount,
        description=f"{bill['category_name']} payment to {bill['provider']} ({bill['consumer_id']})",
        category="Bill",
        reference=f"BILL/{bill['biller_reference']}",
        metadata={
            "provider": bill["provider"], "consumer_id": bill["consumer_id"],
            "biller_reference": bill["biller_reference"], "fee_paise": 0,
            "user_id": user["id"],
        },
    )
    notify(user["id"], "Bill paid successfully",
           f"Rs. {amount/100:,.2f} paid to {bill['provider']}. Ref {bill['biller_reference']}",
           "bill", {"transaction_id": entry["transaction_id"]})
    record_audit(user["id"], "BILL_PAID", bill["provider"], "SUCCESS",
                 {"amount_paise": amount, "biller_reference": bill["biller_reference"]})
    return {
        "entry": entry,
        "bill": {**bill, "status": "PAID"},
        "receipt": {
            "transaction_id": entry["transaction_id"],
            "reference": entry["reference"],
            "biller_reference": bill["biller_reference"],
            "amount_paise": amount,
            "provider": bill["provider"],
            "consumer_id": bill["consumer_id"],
            "due_date": bill["due_date"],
        },
    }
