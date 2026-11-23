"""FR-01..FR-05: ledger mathematical invariants and immutability."""
from __future__ import annotations

import json
import random

import pytest

from backend.app.models.schemas import AccountCreate
from backend.app.services.ledger_service import LedgerError, ledger


def _account(code: str, opening: int = 0, account_type="Asset", allow_negative=False):
    return ledger.create_account(AccountCreate(
        code=code, name=f"Test {code}", account_type=account_type,
        role="Wallet", allow_negative=allow_negative,
        opening_balance_paise=opening,
    ))


def test_balanced_two_line_posting(env):
    a = _account("TEST-TWO-A", 100_000)
    b = _account("TEST-TWO-B", 0)
    entry = ledger.transfer(a["id"], b["id"], 25_000, "Two line test")
    assert entry["total_paise"] == 25_000
    assert len(entry["lines"]) == 2
    assert ledger.balance(a["id"]) == 75_000
    assert ledger.balance(b["id"]) == 25_000


def test_three_line_and_multiline_postings(env):
    a = _account("TEST-3-A", 500_000)
    b = _account("TEST-3-B")
    fee = ledger.get_account("acc_sys_fees")
    entry = ledger.transfer(a["id"], b["id"], 100_000, "Three line fee test", fee_paise=1_500)
    assert len(entry["lines"]) == 3
    debits = sum(l["debit_paise"] for l in entry["lines"])
    credits = sum(l["credit_paise"] for l in entry["lines"])
    assert debits == credits == 101_500
    assert ledger.balance(a["id"]) == 398_500
    assert ledger.balance(b["id"]) == 100_000
    assert ledger.balance(fee["id"]) == 1_500 + 0  # seeded history carries no fees


def test_unbalanced_entry_rejected_via_api(client, operator):
    accounts = ledger.get_accounts()
    source = next(a for a in accounts if a["code"].startswith("SYS-SETTLEMENT"))
    target = next(a for a in accounts if a["role"] == "Wallet")
    bad = {
        "description": "Unbalanced posting",
        "category": "Manual Journal",
        "lines": [
            {"account_id": target["id"], "debit_paise": 10_000, "credit_paise": 0},
            {"account_id": source["id"], "debit_paise": 0, "credit_paise": 9_999},
        ],
    }
    response = client.post("/api/ledger/entries", json=bad)
    assert response.status_code == 400
    assert "Unbalanced entry" in response.json()["detail"]


def test_zero_sum_trial_balance_across_100_random_transactions(env):
    a = _account("TEST-RND-A", 100_000_000)
    b = _account("TEST-RND-B", 100_000_000)
    rng = random.Random(20261123)
    for _ in range(100):
        amount = rng.randint(1, 500_000)
        ledger.transfer(a["id"], b["id"], amount, "Random balanced transfer")
    tb = ledger.trial_balance()
    assert tb.balanced is True
    assert tb.difference_paise == 0
    assert tb.total_debits_paise == tb.total_credits_paise
    assert ledger.balance(a["id"]) + ledger.balance(b["id"]) == 200_000_000


def test_negative_customer_balance_rejected(env):
    a = _account("TEST-NEG-A", 5_000)
    b = _account("TEST-NEG-B")
    with pytest.raises(LedgerError, match="Insufficient balance"):
        ledger.transfer(a["id"], b["id"], 5_001, "Overdraft attempt")
    assert ledger.balance(a["id"]) == 5_000


def test_posted_entry_is_immutable(client, operator, env):
    a = _account("TEST-IMM-A", 10_000)
    b = _account("TEST-IMM-B")
    entry = ledger.transfer(a["id"], b["id"], 1_000, "Immutable entry")
    raw_before = (env / "entries.json").read_text()
    stored = json.loads(raw_before)
    original = next(e for e in stored if e["id"] == entry["id"])
    assert original["description"] == "Immutable entry"

    # No update/delete route exists on the immutable journal.
    assert client.put(f"/api/ledger/entries/{entry['id']}", json={"description": "hacked"}).status_code in (404, 405)
    assert client.delete(f"/api/ledger/entries/{entry['id']}").status_code in (404, 405)
    assert (env / "entries.json").read_text() == raw_before


def test_four_account_types_and_unique_codes(env):
    for idx, account_type in enumerate(("Asset", "Liability", "Income", "Expense")):
        account = _account(f"TEST-TYPE-{idx}", account_type=account_type)
        assert account["account_type"] == account_type
        assert account["active"] is True
    with pytest.raises(LedgerError, match="already exists"):
        _account("TEST-TYPE-0")
