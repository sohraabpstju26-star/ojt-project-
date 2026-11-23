"""FastAPI dependency layer: session resolution and server-side RBAC enforcement."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import Depends, HTTPException, Request, status

from .. import config
from ..services import auth_service


def session_token(request: Request) -> Optional[str]:
    return request.cookies.get(config.SESSION_COOKIE)


def current_auth(request: Request) -> Dict[str, Any]:
    auth = auth_service.resolve_session(session_token(request))
    if not auth or "user" not in auth:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return auth


def get_current_user(auth: Dict[str, Any] = Depends(current_auth)) -> Dict[str, Any]:
    return auth["user"]


def get_session(auth: Dict[str, Any] = Depends(current_auth)) -> Dict[str, Any]:
    return auth["session"]


def require_roles(*roles: str) -> Callable:
    """Server-side RBAC gate. Administrators inherit every permission."""
    def dependency(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if user["role"] == "Administrator" or user["role"] in roles:
            if not user.get("is_active", True):
                raise HTTPException(status_code=403, detail="Account is inactive")
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires one of roles: {', '.join(roles)}",
        )
    return dependency


CustomerOnly = require_roles("Customer", "Merchant")
OperatorOnly = require_roles("Operator")
AuditorOnly = require_roles("Auditor")
LedgerReader = require_roles("Operator", "Auditor")
LedgerWriter = require_roles("Operator")
AdminOnly = require_roles("Administrator")
