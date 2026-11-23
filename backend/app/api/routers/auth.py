"""Authentication endpoints: /api/auth."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ... import config
from ...models.schemas import (
    ChangePasswordIn, LoginIn, MFASetupOut, MFAVerifyIn, RegisterIn, SessionOut,
)
from ...services import auth_service
from ..deps import get_current_user, session_token

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

SECURE_COOKIES = os.environ.get("PAYFLOW_SECURE_COOKIES", "0") == "1"


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=config.SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=SECURE_COOKIES,
        samesite="strict",
        path="/",
        max_age=config.SESSION_SLIDING_HOURS * 3600,
    )


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    return (forwarded.split(",")[0].strip() if forwarded else request.client.host)


@router.post("/register", status_code=201)
def register(payload: RegisterIn, response: Response):
    try:
        result = auth_service.register(payload)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _set_session_cookie(response, result["token"])
    return {"message": "Account created and wallet provisioned", "user": result["user"]}


@router.post("/login")
def login(payload: LoginIn, response: Response, request: Request):
    try:
        result = auth_service.login(payload, ip=_client_ip(request))
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    if result.get("mfa_required"):
        return {"mfa_required": True, "message": "Enter your TOTP code to continue"}
    _set_session_cookie(response, result["token"])
    return {"mfa_required": False, "message": "Login successful", "user": result["user"]}


@router.post("/mfa/setup", response_model=MFASetupOut)
def mfa_setup(user=Depends(get_current_user)):
    return auth_service.setup_mfa(user["id"])


@router.post("/mfa/verify")
def mfa_verify(payload: MFAVerifyIn, response: Response, user=Depends(get_current_user)):
    try:
        result = auth_service.verify_mfa_setup(user["id"], payload.code)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # Privilege elevation: rotate the session and mark it MFA-verified.
    _set_session_cookie(response, auth_service.create_session(user["id"], mfa_verified=True))
    return result


@router.post("/mfa/disable")
def mfa_disable(payload: MFAVerifyIn, user=Depends(get_current_user)):
    try:
        return auth_service.disable_mfa(user["id"], payload.code)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/logout")
def logout(response: Response, token=Depends(session_token)):
    auth_service.logout(token)
    response.delete_cookie(config.SESSION_COOKIE, path="/")
    return {"message": "Session revoked"}


@router.get("/session", response_model=SessionOut)
def session(request: Request):
    auth = auth_service.resolve_session(session_token(request))
    if not auth or "user" not in auth:
        raise HTTPException(status_code=401, detail="No active session")
    user = auth["user"]
    session_info = {
        k: v for k, v in auth["session"].items() if k != "token_hash"
    }
    return {
        "authenticated": True,
        "user": auth_service._public_user(user),
        "permissions": auth_service.permissions_for(user["role"]),
        "session": session_info,
    }


@router.post("/change-password")
def change_password(payload: ChangePasswordIn, user=Depends(get_current_user)):
    try:
        auth_service.change_password(user["id"], payload.current_password, payload.new_password)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": "Password updated"}
