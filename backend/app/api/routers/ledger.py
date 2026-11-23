"""Double-entry ledger endpoints: /api/ledger."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ...models.schemas import AccountCreate, AccountOut, EntryOut, JournalEntryIn, RefundIn, ReverseIn, TrialBalanceResponse
from ...services import audit_service
from ...services.ledger_service import LedgerError, ledger
from ..deps import LedgerReader, LedgerWriter, get_current_user

router = APIRouter(prefix="/api/ledger", tags=["Double-Entry Ledger"])


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(user_id: str | None = None, user=Depends(LedgerReader)):
    return ledger.get_accounts(user_id=user_id)


@router.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(payload: AccountCreate, user=Depends(LedgerWriter)):
    try:
        account = ledger.create_account(payload)
    except LedgerError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit_service.record_audit(user["id"], "LEDGER_ACCOUNT_CREATED", account["id"], "SUCCESS")
    return account


@router.post("/accounts/{account_id}/toggle")
def toggle_account(account_id: str, active: bool = True, user=Depends(LedgerWriter)):
    try:
        account = ledger.set_account_active(account_id, active)
    except LedgerError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit_service.record_audit(user["id"], "ACCOUNT_TOGGLED", account_id, "SUCCESS", {"active": active})
    return account


@router.get("/accounts/{account_id}")
def get_account(account_id: str, user=Depends(LedgerReader)):
    account = ledger.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return {**account, "balance_paise": ledger.balance(account_id)}


@router.get("/entries", response_model=list[EntryOut])
def list_entries(account_id: str | None = None, category: str | None = None,
                 start_date: str | None = None, end_date: str | None = None,
                 user=Depends(LedgerReader)):
    return ledger.get_transaction_history(account_id, category, start_date, end_date)


@router.post("/entries", response_model=EntryOut, status_code=201)
def post_entry(payload: JournalEntryIn, user=Depends(LedgerWriter)):
    try:
        entry = ledger.post_entry(
            description=payload.description,
            lines=[l.model_dump() for l in payload.lines],
            category=payload.category,
            reference=payload.reference,
            transaction_id=payload.transaction_id,
            metadata=payload.metadata,
        )
    except LedgerError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit_service.record_audit(user["id"], "MANUAL_JOURNAL_POSTED", entry["transaction_id"], "SUCCESS")
    return entry


@router.get("/trial-balance", response_model=TrialBalanceResponse)
def trial_balance(user=Depends(LedgerReader)):
    return ledger.trial_balance()


@router.post("/reverse/{transaction_id}", response_model=EntryOut)
def reverse(transaction_id: str, payload: ReverseIn | None = None, user=Depends(LedgerWriter)):
    try:
        entry = ledger.reverse(transaction_id, (payload.reason if payload else "Operational reversal"), user["id"])
    except LedgerError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit_service.record_audit(user["id"], "ENTRY_REVERSED", transaction_id, "SUCCESS")
    return entry


@router.post("/refund/{transaction_id}", response_model=EntryOut)
def refund(transaction_id: str, payload: RefundIn | None = None, user=Depends(LedgerWriter)):
    try:
        entry = ledger.refund(
            transaction_id,
            refund_amount_paise=(payload.refund_amount_paise if payload else None),
            reason=(payload.reason if payload else "Merchant Refund"),
            operator_id=user["id"],
        )
    except LedgerError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit_service.record_audit(user["id"], "REFUND_ISSUED", transaction_id, "SUCCESS")
    return entry


@router.post("/recalculate-balances")
def recalculate(user=Depends(LedgerWriter)):
    balances = ledger.calculate_balances()
    return {"status": "OK", "accounts": len(balances)}
