"""Utility bill endpoints: /api/bills."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...models.schemas import BillFetchIn, BillPayIn
from ...services import bill_service
from ...services.auth_service import StepUpRequired
from ...services.payment_service import PaymentError
from ...services.ledger_service import LedgerError
from ..deps import CustomerOnly, get_current_user, get_session

router = APIRouter(prefix="/api/bills", tags=["Bills & Recharges"])


@router.get("/categories")
def list_categories(user=Depends(get_current_user)):
    return bill_service.categories()


@router.post("/fetch")
def fetch_bill(payload: BillFetchIn, user=Depends(CustomerOnly)):
    try:
        return bill_service.fetch_bill(payload)
    except bill_service.BillError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/pay")
def pay_bill(payload: BillPayIn, user=Depends(CustomerOnly), session=Depends(get_session)):
    try:
        return bill_service.pay_bill(user, session, payload)
    except StepUpRequired as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except (bill_service.BillError, PaymentError, LedgerError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
