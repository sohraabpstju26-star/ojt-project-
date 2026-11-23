"""Payment endpoints: /api/payments."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse

from ...core.json_store import stores
from ...models.schemas import QRRequest, ReceiptOut, ScanPayIn, SendMoneyIn
from ...services import payment_service
from ...services.auth_service import StepUpRequired
from ...services.ledger_service import LedgerError
from ..deps import CustomerOnly, get_current_user, get_session, require_roles

router = APIRouter(prefix="/api/payments", tags=["Payments"])


def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, StepUpRequired):
        return HTTPException(status_code=403, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.post("/send")
def send_money(payload: SendMoneyIn, request: Request,
               user=Depends(CustomerOnly), session=Depends(get_session)):
    try:
        return payment_service.send_money(user, session, payload, ip=request.client.host)
    except (payment_service.PaymentError, LedgerError, StepUpRequired) as exc:
        raise _map(exc)


@router.post("/scan-pay")
def scan_pay(payload: ScanPayIn, request: Request,
             user=Depends(require_roles("Customer")), session=Depends(get_session)):
    try:
        return payment_service.scan_pay(user, session, payload, ip=request.client.host)
    except (payment_service.PaymentError, LedgerError, StepUpRequired) as exc:
        raise _map(exc)


@router.get("/qr")
def get_qr(amount_paise: int | None = Query(default=None, ge=1), note: str | None = None,
           user=Depends(get_current_user)):
    payload = payment_service.qr_payload(user, amount_paise, note)
    return {
        "vpa": user["vpa"],
        "name": user["full_name"],
        "payload": payload,
        "svg": payment_service.qr_payload_to_svg(payload),
        "static_payload": payment_service.qr_payload(user),
    }


@router.get("/qr/image", response_class=HTMLResponse)
def get_qr_image(amount_paise: int | None = Query(default=None, ge=1), note: str | None = None,
                 user=Depends(get_current_user)):
    payload = payment_service.qr_payload(user, amount_paise, note)
    return HTMLResponse(payment_service.qr_payload_to_svg(payload))


@router.get("/receipt/{transaction_id}", response_model=ReceiptOut)
def get_receipt(transaction_id: str, user=Depends(get_current_user)):
    try:
        return payment_service.receipt_for(transaction_id, user["id"])
    except payment_service.PaymentError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/receipt/{transaction_id}/download", response_class=HTMLResponse)
def download_receipt(transaction_id: str, user=Depends(get_current_user)):
    try:
        receipt = payment_service.receipt_for(transaction_id, user["id"])
    except payment_service.PaymentError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return HTMLResponse(payment_service.receipt_html(receipt))


@router.get("/merchants")
def list_merchants(user=Depends(get_current_user)):
    return stores.merchants.read()
