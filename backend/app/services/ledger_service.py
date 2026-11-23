"""PAYFLOW immutable double-entry ledger engine.

All monetary values are integer paise. No floating point ever touches a balance.
Every posting is validated (debits == credits), append-only, and serialised by a
coarse advisory lock. Corrections are new balanced reversal/refund entries only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .. import config
from ..core.file_lock import ledger_lock
from ..core.json_store import stores
from ..core.security import new_id, new_transaction_id
from ..models.schemas import TrialBalanceResponse, TrialAccountLine
from ..config import utc_now_iso

DEBIT_NORMAL = {"Asset", "Expense"}


class LedgerError(ValueError):
    """Raised for any invariant violation; mapped to HTTP 400 by the API."""


class Ledger:
    """Standalone, append-only, integer-paise double-entry ledger."""

    # -- Accounts ------------------------------------------------------------
    def create_account(self, account_in) -> Dict[str, Any]:
        payload = account_in.model_dump() if hasattr(account_in, "model_dump") else dict(account_in)
        with ledger_lock():
            accounts = stores.accounts.read()
            if any(a["code"] == payload["code"] for a in accounts):
                raise LedgerError(f"Account code already exists: {payload['code']}")
            account = {
                "id": new_id("acc"),
                "code": payload["code"],
                "name": payload["name"],
                "account_type": payload["account_type"],
                "role": payload["role"],
                "user_id": payload.get("user_id"),
                "allow_negative": bool(payload.get("allow_negative", False)),
                "opening_balance_paise": int(payload.get("opening_balance_paise", 0) or 0),
                "active": True,
                "created_at": utc_now_iso(),
            }
            accounts.append(account)
            stores.accounts.write(accounts)
            current = stores.balances.read()
            current[account["id"]] = account["opening_balance_paise"]
            stores.balances.write(current)
            return account

    def create_account_with_id(self, account: Dict[str, Any]) -> Dict[str, Any]:
        """Provision an account with a deterministic id (used by bootstrap)."""
        with ledger_lock():
            accounts = stores.accounts.read()
            if any(a["id"] == account["id"] or a["code"] == account["code"] for a in accounts):
                return next(a for a in accounts if a["id"] == account["id"])
            record = dict(account)
            record.setdefault("active", True)
            record.setdefault("created_at", utc_now_iso())
            accounts.append(record)
            stores.accounts.write(accounts)
            current = stores.balances.read()
            current[record["id"]] = record.get("opening_balance_paise", 0)
            stores.balances.write(current)
            return record

    def get_account(self, account_id: str) -> Optional[Dict[str, Any]]:
        with ledger_lock():
            return next((a for a in stores.accounts.read() if a["id"] == account_id), None)

    def get_accounts(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with ledger_lock():
            accounts = stores.accounts.read()
            if user_id is not None:
                accounts = [a for a in accounts if a.get("user_id") == user_id]
            balances = self._compute_balances_unlocked()
            return [{**a, "balance_paise": balances.get(a["id"], a.get("opening_balance_paise", 0))} for a in accounts]

    def set_account_active(self, account_id: str, active: bool) -> Dict[str, Any]:
        with ledger_lock():
            accounts = stores.accounts.read()
            for a in accounts:
                if a["id"] == account_id:
                    a["active"] = active
                    stores.accounts.write(accounts)
                    return a
        raise LedgerError(f"Account not found: {account_id}")

    # -- Validation ----------------------------------------------------------
    def validate_entry(self, lines: List[Dict[str, Any]], skip_balance_check: bool = False) -> int:
        """Validate line structure, polarity, balance and funds. Return total paise."""
        if not isinstance(lines, list) or len(lines) < 2:
            raise LedgerError("A journal entry requires at least two line items")

        accounts = {a["id"]: a for a in stores.accounts.read()}
        total_debits = 0
        total_credits = 0
        movements: Dict[str, int] = {}

        for raw in lines:
            line = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw)
            account_id = line.get("account_id")
            debit = line.get("debit_paise", 0)
            credit = line.get("credit_paise", 0)
            if not isinstance(debit, int) or not isinstance(credit, int):
                raise LedgerError("Monetary amounts must be integer paise")
            if debit < 0 or credit < 0:
                raise LedgerError("Line amounts cannot be negative")
            if debit > 0 and credit > 0:
                raise LedgerError("A line may not be both debit and credit")
            if debit == 0 and credit == 0:
                raise LedgerError("A line must have a non-zero amount")
            account = accounts.get(account_id)
            if account is None:
                raise LedgerError(f"Unknown account: {account_id}")
            if not account.get("active", True):
                raise LedgerError(f"Inactive account: {account_id}")
            total_debits += debit
            total_credits += credit
            delta = debit - credit if account["account_type"] in DEBIT_NORMAL else credit - debit
            movements[account_id] = movements.get(account_id, 0) + delta

        if total_debits != total_credits:
            raise LedgerError(
                f"Unbalanced entry: debits {total_debits} paise != credits {total_credits} paise"
            )

        if not skip_balance_check:
            current = stores.balances.read()
            for account_id, delta in movements.items():
                account = accounts[account_id]
                projected = current.get(account_id, account.get("opening_balance_paise", 0)) + delta
                if projected < 0 and not account.get("allow_negative", False):
                    raise LedgerError(
                        f"Insufficient balance in {account['code']}: projected {projected} paise"
                    )
        return total_debits

    # -- Balances ------------------------------------------------------------
    def _compute_balances_unlocked(self) -> Dict[str, int]:
        accounts = stores.accounts.read()
        balances = {a["id"]: int(a.get("opening_balance_paise", 0)) for a in accounts}
        polarity = {a["id"]: a["account_type"] for a in accounts}
        for entry in stores.entries.read():
            for line in entry.get("lines", []):
                aid = line.get("account_id")
                if aid not in balances:
                    continue
                debit = int(line.get("debit_paise", 0))
                credit = int(line.get("credit_paise", 0))
                if polarity[aid] in DEBIT_NORMAL:
                    balances[aid] += debit - credit
                else:
                    balances[aid] += credit - debit
        return balances

    def calculate_balances(self) -> Dict[str, int]:
        with ledger_lock():
            balances = self._compute_balances_unlocked()
            stores.balances.write(balances)
            return balances

    def balance(self, account_id: str) -> int:
        with ledger_lock():
            cached = stores.balances.read()
            if account_id in cached:
                return int(cached[account_id])
            return self._compute_balances_unlocked().get(account_id, 0)

    def reconcile_cache(self) -> None:
        self.calculate_balances()

    # -- Posting -------------------------------------------------------------
    def post_entry(
        self,
        description: str,
        lines: List[Dict[str, Any]],
        category: str,
        reference: Optional[str] = None,
        transaction_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        is_reversal: bool = False,
        reversed_entry_id: Optional[str] = None,
        skip_balance_check: bool = False,
        occurred_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        with ledger_lock():
            total = self.validate_entry(lines, skip_balance_check=skip_balance_check)
            entries = stores.entries.read()
            existing_ids = {e.get("transaction_id") for e in entries}
            if transaction_id:
                if transaction_id in existing_ids:
                    raise LedgerError(f"Duplicate transaction id: {transaction_id}")
                txn_id = transaction_id
            else:
                txn_id = new_transaction_id()
                for _ in range(10):
                    if txn_id not in existing_ids:
                        break
                    txn_id = new_transaction_id()
                else:
                    raise LedgerError("Unable to allocate a unique transaction id")
            if reference is not None and any(e.get("reference") == reference for e in entries):
                raise LedgerError(f"Duplicate reference: {reference}")

            stamp = occurred_at or utc_now_iso()
            date_part = stamp[:10]
            normalised_lines = []
            for raw in lines:
                line = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw)
                normalised_lines.append(
                    {
                        "account_id": line["account_id"],
                        "debit_paise": int(line.get("debit_paise", 0)),
                        "credit_paise": int(line.get("credit_paise", 0)),
                        "description": line.get("description", description),
                    }
                )

            entry = {
                "id": new_id("ent"),
                "date": date_part,
                "timestamp": stamp,
                "transaction_id": txn_id,
                "reference": reference,
                "description": description,
                "category": category,
                "total_paise": total,
                "lines": normalised_lines,
                "metadata": metadata or {},
                "is_reversal": is_reversal,
                "reversed_entry_id": reversed_entry_id,
            }
            entries.append(entry)
            stores.entries.write(entries)
            stores.balances.write(self._compute_balances_unlocked())
            return entry

    # -- High-level operations ----------------------------------------------
    def transfer(
        self,
        from_account_id: str,
        to_account_id: str,
        amount_paise: int,
        description: str,
        category: str = "P2P Transfer",
        reference: Optional[str] = None,
        fee_paise: int = 0,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        if not isinstance(amount_paise, int) or amount_paise <= 0:
            raise LedgerError("Transfer amount must be a positive integer in paise")
        if not isinstance(fee_paise, int) or fee_paise < 0:
            raise LedgerError("Fee must be a non-negative integer in paise")
        if from_account_id == to_account_id:
            raise LedgerError("Cannot transfer to the same account")

        lines = [
            {
                "account_id": to_account_id,
                "debit_paise": amount_paise,
                "credit_paise": 0,
                "description": f"Credit to destination: {description}",
            },
            {
                "account_id": from_account_id,
                "debit_paise": 0,
                "credit_paise": amount_paise + fee_paise,
                "description": f"Debit from source: {description}",
            },
        ]
        if fee_paise:
            lines.append(
                {
                    "account_id": config.SYSTEM_FEES_ACCOUNT,
                    "debit_paise": fee_paise,
                    "credit_paise": 0,
                    "description": "Platform fee clearing",
                }
            )
        meta = dict(metadata or {})
        meta.setdefault("fee_paise", fee_paise)
        return self.post_entry(
            description=description,
            lines=lines,
            category=category,
            reference=reference,
            metadata=meta,
        )

    def top_up(
        self,
        account_id: str,
        amount_paise: int,
        funding_source_account_id: str = config.SYSTEM_SETTLEMENT_ACCOUNT,
        description: str = "Wallet Top-up",
        reference: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        if not isinstance(amount_paise, int) or amount_paise <= 0:
            raise LedgerError("Top-up amount must be a positive integer in paise")
        lines = [
            {"account_id": account_id, "debit_paise": amount_paise, "credit_paise": 0,
             "description": "Wallet funding"},
            {"account_id": funding_source_account_id, "debit_paise": 0,
             "credit_paise": amount_paise, "description": "Settlement reserve outflow"},
        ]
        return self.post_entry(
            description=description, lines=lines, category="Top-up",
            reference=reference, metadata=metadata,
        )

    def _wallet_for_vpa(self, vpa: str) -> Optional[str]:
        users = stores.users.read()
        user = next((u for u in users if u.get("vpa") == vpa), None)
        if not user:
            return None
        wallet = next(
            (w for w in stores.wallets.read() if w.get("user_id") == user["id"] and w.get("is_primary")),
            None,
        )
        return wallet["account_id"] if wallet else None

    def _parties_from_entry(self, entry: Dict[str, Any]) -> tuple[str, str]:
        """Return (payer_account_id, receiver_account_id) for an asset transfer."""
        accounts = {a["id"]: a for a in stores.accounts.read()}
        payer = receiver = None
        for line in entry.get("lines", []):
            acc = accounts.get(line["account_id"], {})
            if acc.get("account_type") not in DEBIT_NORMAL:
                continue
            if line.get("credit_paise", 0) > 0 and payer is None:
                payer = line["account_id"]
            if line.get("debit_paise", 0) > 0 and receiver is None:
                receiver = line["account_id"]
        return payer, receiver

    def refund(
        self,
        original_transaction_id: str,
        refund_amount_paise: Optional[int] = None,
        reason: str = "Merchant Refund",
        operator_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        with ledger_lock():
            entries = stores.entries.read()
            original = next(
                (e for e in entries if e.get("transaction_id") == original_transaction_id), None
            )
            if original is None:
                raise LedgerError(f"Unknown transaction: {original_transaction_id}")
            if original.get("category") in ("Refund", "Reversal"):
                raise LedgerError("Cannot refund a refund/reversal entry")
            already = sum(
                e.get("total_paise", 0)
                for e in entries
                if e.get("category") == "Refund"
                and e.get("metadata", {}).get("original_transaction_id") == original_transaction_id
            )
            remaining = original["total_paise"] - already
            if remaining <= 0:
                raise LedgerError("Original transaction has been fully refunded")
            amount = remaining if refund_amount_paise is None else int(refund_amount_paise)
            if not isinstance(amount, int) or amount <= 0:
                raise LedgerError("Refund amount must be a positive integer")
            if amount > remaining:
                raise LedgerError(f"Refund exceeds available amount: {remaining} paise")

            payer, receiver = self._parties_from_entry(original)
            if not payer or not receiver:
                raise LedgerError("Original transaction has no refundable wallet parties")
            lines = [
                {"account_id": payer, "debit_paise": amount, "credit_paise": 0,
                 "description": f"Refund credit: {reason}"},
                {"account_id": receiver, "debit_paise": 0, "credit_paise": amount,
                 "description": f"Refund debit: {reason}"},
            ]
            meta = {
                "original_transaction_id": original_transaction_id,
                "reason": reason,
                "operator_id": operator_id,
                "refund_of_entry_id": original["id"],
            }
            return self.post_entry(
                description=f"Refund for {original_transaction_id}: {reason}",
                lines=lines, category="Refund", metadata=meta,
            )

    def reverse(
        self,
        original_transaction_id: str,
        reason: str,
        operator_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        with ledger_lock():
            entries = stores.entries.read()
            original = next(
                (e for e in entries if e.get("transaction_id") == original_transaction_id), None
            )
            if original is None:
                raise LedgerError(f"Unknown transaction: {original_transaction_id}")
            if original.get("is_reversal"):
                raise LedgerError("Cannot reverse a reversal entry")
            duplicate = next(
                (e for e in entries if e.get("reversed_entry_id") == original["id"] and e.get("is_reversal")),
                None,
            )
            if duplicate:
                raise LedgerError(f"Transaction already reversed by {duplicate['transaction_id']}")

            inverted = []
            for line in original.get("lines", []):
                inverted.append(
                    {
                        "account_id": line["account_id"],
                        "debit_paise": int(line.get("credit_paise", 0)),
                        "credit_paise": int(line.get("debit_paise", 0)),
                        "description": f"Reversal of: {line.get('description', '')}",
                    }
                )
            meta = {
                "reason": reason,
                "operator_id": operator_id,
                "reversed_transaction_id": original_transaction_id,
            }
            return self.post_entry(
                description=f"Reversal of {original_transaction_id}: {reason}",
                lines=inverted, category="Reversal", metadata=meta,
                is_reversal=True, reversed_entry_id=original["id"],
                skip_balance_check=True,
            )

    # -- Queries -------------------------------------------------------------
    def get_transaction_history(
        self,
        account_id: Optional[str] = None,
        category: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with ledger_lock():
            results = stores.entries.read()
            if account_id:
                results = [e for e in results if any(l["account_id"] == account_id for l in e["lines"])]
            if category:
                results = [e for e in results if e.get("category") == category]
            if start_date:
                results = [e for e in results if e.get("date", "") >= start_date]
            if end_date:
                results = [e for e in results if e.get("date", "") <= end_date]
            return sorted(results, key=lambda e: e.get("timestamp", ""), reverse=True)

    def get_entry(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        with ledger_lock():
            return next(
                (e for e in stores.entries.read() if e.get("transaction_id") == transaction_id), None
            )

    def trial_balance(self) -> TrialBalanceResponse:
        with ledger_lock():
            accounts = stores.accounts.read()
            entries = stores.entries.read()
            balances = self._compute_balances_unlocked()
            total_debits = sum(
                int(l.get("debit_paise", 0)) for e in entries for l in e.get("lines", [])
            )
            total_credits = sum(
                int(l.get("credit_paise", 0)) for e in entries for l in e.get("lines", [])
            )
            per_account: Dict[str, Dict[str, int]] = {}
            for e in entries:
                for l in e.get("lines", []):
                    row = per_account.setdefault(
                        l["account_id"], {"debits": 0, "credits": 0}
                    )
                    row["debits"] += int(l.get("debit_paise", 0))
                    row["credits"] += int(l.get("credit_paise", 0))
            lines = [
                TrialAccountLine(
                    account_id=a["id"],
                    code=a["code"],
                    name=a["name"],
                    account_type=a["account_type"],
                    total_debits=per_account.get(a["id"], {}).get("debits", 0),
                    total_credits=per_account.get(a["id"], {}).get("credits", 0),
                    balance_paise=balances.get(a["id"], a.get("opening_balance_paise", 0)),
                )
                for a in accounts
            ]
            difference = total_debits - total_credits
            return TrialBalanceResponse(
                total_debits_paise=total_debits,
                total_credits_paise=total_credits,
                difference_paise=difference,
                balanced=difference == 0,
                account_count=len(accounts),
                entries_count=len(entries),
                accounts=lines,
            )


ledger = Ledger()
