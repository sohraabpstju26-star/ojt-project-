"""Concurrent spending and atomic-write stress under advisory locks."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.app.core.json_store import JSONStore
from backend.app.models.schemas import AccountCreate
from backend.app.services.ledger_service import LedgerError, ledger


def _account(code, opening):
    return ledger.create_account(AccountCreate(
        code=code, name=code, account_type="Asset", role="Wallet",
        allow_negative=False, opening_balance_paise=opening,
    ))


def test_simultaneous_transfers_cannot_double_spend(env):
    source = _account("CONC-SRC", 100_000)
    target = _account("CONC-DST", 0)
    amount = 20_000
    attempts = 8

    def spend(_):
        try:
            ledger.transfer(source["id"], target["id"], amount, "Concurrent spend")
            return True
        except LedgerError:
            return False

    with ThreadPoolExecutor(max_workers=attempts) as pool:
        results = list(pool.map(spend, range(attempts)))

    assert sum(results) == 5  # only 100,000 paise available
    assert ledger.balance(source["id"]) == 0
    assert ledger.balance(target["id"]) == 100_000
    tb = ledger.trial_balance()
    assert tb.balanced and tb.difference_paise == 0


def test_atomic_json_writes_preserve_every_record(env):
    store = JSONStore("concurrency_test.json", [])
    total = 120

    def append(idx):
        store.append({"index": idx})

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(append, range(total)))

    records = store.read()
    assert len(records) == total
    assert {r["index"] for r in records} == set(range(total))
