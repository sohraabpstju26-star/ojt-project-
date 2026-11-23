"""P2P, wallets, collect requests, refunds and reversals end-to-end."""
from __future__ import annotations


def _wallets(client):
    response = client.get("/api/wallets")
    assert response.status_code == 200
    return response.json()


def _primary(client):
    return next(w for w in _wallets(client) if w["is_primary"])


def test_p2p_transfer_moves_funds_between_customers(client, login):
    aditi = login("aditi_sharma", "Customer@123")
    before = _primary(client)["balance_paise"]
    response = client.post("/api/payments/send", json={
        "recipient": "rohit_kumar@payflow", "amount_paise": 100_000,
        "note": "Test payment",
    })
    assert response.status_code == 200, response.text
    assert _primary(client)["balance_paise"] == before - 100_000

    rohit = login("rohit_kumar", "Customer@123")
    assert rohit["id"] != aditi["id"]
    # Seeded history: -150000 (to Aditi), +75000 (from Aditi), -22000 (Starbucks QR)
    assert _primary(client)["balance_paise"] == 2_500_000 + 100_000 + 75_000 - 150_000 - 22_000


def test_insufficient_funds_rejected(client, customer):
    response = client.post("/api/payments/send", json={
        "recipient": "rohit_kumar@payflow", "amount_paise": 999_999_999,
    })
    assert response.status_code == 400
    assert "Insufficient balance" in response.json()["detail"]


def test_duplicate_transaction_reference_prevention(client, operator):
    from backend.app.core.json_store import stores
    settlement = next(a for a in stores.accounts.read() if a["code"] == "SYS-SETTLEMENT")
    from backend.app.services.ledger_service import ledger
    payload = dict(
        description="Duplicate reference test", category="Manual Journal",
        reference="DUP/REF/TEST/001",
        lines=[
            {"account_id": settlement["id"], "debit_paise": 100, "credit_paise": 0},
            {"account_id": "acc_sys_fees", "debit_paise": 0, "credit_paise": 100},
        ],
    )
    first = client.post("/api/ledger/entries", json=payload)
    assert first.status_code == 201, first.text
    second = client.post("/api/ledger/entries", json=payload)
    assert second.status_code == 400
    assert "Duplicate reference" in second.json()["detail"]


def test_payment_request_approval_and_rejection(client, login):
    login("aditi_sharma", "Customer@123")
    created = client.post("/api/requests", json={
        "payer": "rohit_kumar@payflow", "amount_paise": 50_000, "note": "Collect test",
    })
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]

    login("rohit_kumar", "Customer@123")
    incoming = [r for r in client.get("/api/requests").json() if r["direction"] == "INCOMING"]
    assert any(r["id"] == request_id for r in incoming)
    approved = client.post(f"/api/requests/{request_id}/approve", json={})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"

    login("aditi_sharma", "Customer@123")
    second = client.post("/api/requests", json={
        "payer": "rohit_kumar@payflow", "amount_paise": 20_000, "note": "Decline test",
    }).json()["id"]
    login("rohit_kumar", "Customer@123")
    rejected = client.post(f"/api/requests/{second}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"


def test_full_and_partial_merchant_refunds(client, operator):
    from backend.app.core.json_store import stores
    entries = stores.entries.read()
    full_txn = next(e["transaction_id"] for e in entries if e["category"] == "P2P Transfer")
    partial_txn = next(e["transaction_id"] for e in entries if e["category"] == "Merchant Payment")

    full = client.post(f"/api/ledger/refund/{full_txn}", json={"reason": "Full refund test"})
    assert full.status_code == 200, full.text
    original = next(e for e in stores.entries.read() if e["transaction_id"] == full_txn)
    assert full.json()["total_paise"] == original["total_paise"]

    duplicate = client.post(f"/api/ledger/refund/{full_txn}", json={"reason": "Again"})
    assert duplicate.status_code == 400

    original_partial = next(e for e in stores.entries.read() if e["transaction_id"] == partial_txn)
    half = original_partial["total_paise"] // 2
    part = client.post(f"/api/ledger/refund/{partial_txn}",
                       json={"refund_amount_paise": half, "reason": "Partial"})
    assert part.status_code == 200
    assert part.json()["total_paise"] == half
    remainder = client.post(f"/api/ledger/refund/{partial_txn}", json={"reason": "Remainder"})
    assert remainder.status_code == 200


def test_reversal_and_double_reversal_prevention(client, operator):
    from backend.app.core.json_store import stores
    entries = stores.entries.read()
    txn = next(e["transaction_id"] for e in entries if e["category"] == "Merchant Payment")
    first = client.post(f"/api/ledger/reverse/{txn}", json={"reason": "Chargeback"})
    assert first.status_code == 200, first.text
    assert first.json()["is_reversal"] is True
    assert first.json()["reversed_entry_id"] is not None

    second = client.post(f"/api/ledger/reverse/{txn}", json={"reason": "Again"})
    assert second.status_code == 400
    assert "already reversed" in second.json()["detail"]


def test_wallet_to_wallet_transfer_with_fee(client, customer):
    created = client.post("/api/wallets", json={"label": "Travel Wallet"})
    assert created.status_code == 201, created.text
    secondary = created.json()
    source = _primary(client)
    before = source["balance_paise"]
    response = client.post("/api/wallets/transfer", json={
        "from_wallet_id": source["id"], "to_wallet_id": secondary["id"],
        "amount_paise": 100_000, "fee_paise": 500,
        "description": "Savings allocation",
    })
    assert response.status_code == 200, response.text
    assert _primary(client)["balance_paise"] == before - 100_500
    moved = next(w for w in _wallets(client) if w["id"] == secondary["id"])
    assert moved["balance_paise"] == 100_000
