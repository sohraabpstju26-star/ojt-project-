"""Collect-request endpoints: /api/requests."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...models.schemas import PaymentRequestOut, RequestApproveIn, RequestCreateIn
from ...services import request_service
from ...services.auth_service import StepUpRequired
from ...services.payment_service import PaymentError
from ...services.ledger_service import LedgerError
from ..deps import CustomerOnly, get_current_user, get_session

router = APIRouter(prefix="/api/requests", tags=["Payment Requests"])


@router.get("", response_model=list[PaymentRequestOut])
def list_requests(user=Depends(get_current_user)):
    return request_service.list_requests(user["id"])


@router.post("", response_model=PaymentRequestOut, status_code=201)
def create_request(payload: RequestCreateIn, user=Depends(CustomerOnly)):
    try:
        return request_service.create_request(user, payload)
    except (PaymentError, LedgerError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{request_id}/approve", response_model=PaymentRequestOut)
def approve_request(request_id: str, payload: RequestApproveIn | None = None,
                    user=Depends(CustomerOnly), session=Depends(get_session)):
    try:
        return request_service.approve_request(request_id, user, session, payload)
    except (request_service.RequestError, PaymentError, LedgerError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except StepUpRequired as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{request_id}/reject", response_model=PaymentRequestOut)
def reject_request(request_id: str, user=Depends(CustomerOnly)):
    try:
        return request_service.reject_request(request_id, user)
    except request_service.RequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{request_id}/cancel", response_model=PaymentRequestOut)
def cancel_request(request_id: str, user=Depends(CustomerOnly)):
    try:
        return request_service.cancel_request(request_id, user)
    except request_service.RequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
