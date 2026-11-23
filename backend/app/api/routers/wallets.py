"""Wallet endpoints: /api/wallets."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...models.schemas import OwnTransferIn, TopUpIn, WalletCreateIn, WalletOut
from ...services import wallet_service
from ..deps import CustomerOnly, get_current_user

router = APIRouter(prefix="/api/wallets", tags=["Wallets"])


@router.get("", response_model=list[WalletOut])
def list_wallets(user=Depends(get_current_user)):
    return wallet_service.list_wallets(user["id"])


@router.post("", response_model=WalletOut, status_code=201)
def create_wallet(payload: WalletCreateIn, user=Depends(CustomerOnly)):
    try:
        return wallet_service.create_wallet(user, payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/top-up")
def top_up(payload: TopUpIn, user=Depends(CustomerOnly)):
    try:
        return wallet_service.top_up(user, payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/transfer")
def internal_transfer(payload: OwnTransferIn, user=Depends(CustomerOnly)):
    try:
        return wallet_service.internal_transfer(user, payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
