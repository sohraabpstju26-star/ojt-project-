"""Beneficiary endpoints: /api/beneficiaries."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...models.schemas import BeneficiaryIn, BeneficiaryOut, BeneficiaryUpdateIn
from ...services import beneficiary_service
from ..deps import CustomerOnly, get_current_user

router = APIRouter(prefix="/api/beneficiaries", tags=["Beneficiaries"])


@router.get("", response_model=list[BeneficiaryOut])
def list_beneficiaries(user=Depends(CustomerOnly)):
    return beneficiary_service.list_beneficiaries(user["id"])


@router.post("", response_model=BeneficiaryOut, status_code=201)
def add_beneficiary(payload: BeneficiaryIn, user=Depends(CustomerOnly)):
    try:
        return beneficiary_service.add_beneficiary(user, payload)
    except (beneficiary_service.BeneficiaryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/{beneficiary_id}", response_model=BeneficiaryOut)
def update_beneficiary(beneficiary_id: str, payload: BeneficiaryUpdateIn,
                       user=Depends(CustomerOnly)):
    try:
        return beneficiary_service.update_beneficiary(user, beneficiary_id, payload)
    except beneficiary_service.BeneficiaryError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{beneficiary_id}", status_code=204)
def delete_beneficiary(beneficiary_id: str, user=Depends(CustomerOnly)):
    beneficiary_service.delete_beneficiary(user, beneficiary_id)


@router.post("/{beneficiary_id}/favorite", response_model=BeneficiaryOut)
def toggle_favorite(beneficiary_id: str, user=Depends(CustomerOnly)):
    try:
        return beneficiary_service.toggle_favorite(user, beneficiary_id)
    except beneficiary_service.BeneficiaryError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{beneficiary_id}/history")
def beneficiary_history(beneficiary_id: str, user=Depends(CustomerOnly)):
    try:
        return beneficiary_service.beneficiary_history(user["id"], beneficiary_id)
    except beneficiary_service.BeneficiaryError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
