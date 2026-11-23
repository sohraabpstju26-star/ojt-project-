"""Administration, audit and system-health endpoints: /api/admin."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ... import config
from ...core.json_store import stores
from ...models.schemas import RoleChangeIn, UserOut
from ...services import audit_service, auth_service
from ...services.analytics_service import reconciliation as compute_reconciliation
from ...services.ledger_service import ledger
from ..deps import AdminOnly, AuditorOnly, get_current_user

router = APIRouter(prefix="/api/admin", tags=["Administration & Audit"])


def _public(user: dict) -> dict:
    return auth_service._public_user(user)


@router.get("/users", response_model=list[UserOut])
def list_users(admin=Depends(AdminOnly)):
    balances = {}
    for wallet in stores.wallets.read():
        if wallet.get("is_primary"):
            balances[wallet["user_id"]] = ledger.balance(wallet["account_id"])
    return [{**_public(u), "balance_paise": balances.get(u["id"], 0)} for u in stores.users.read()]


@router.put("/users/{user_id}/role", response_model=UserOut)
def change_role(user_id: str, payload: RoleChangeIn, admin=Depends(AdminOnly)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    result = {}

    def mutate(users):
        for u in users:
            if u["id"] == user_id:
                u["role"] = payload.role
                u["updated_at"] = config.utc_now_iso()
                result.update(u)
    stores.users.mutate(mutate)
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    audit_service.record_audit(admin["id"], "ROLE_CHANGED", user_id, "SUCCESS", {"role": payload.role})
    return _public(result)


@router.post("/users/{user_id}/unlock", response_model=UserOut)
def unlock_user(user_id: str, admin=Depends(AdminOnly)):
    result = {}

    def mutate(users):
        for u in users:
            if u["id"] == user_id:
                u["failed_login_attempts"] = 0
                u["locked_until"] = None
                u["is_active"] = True
                u["updated_at"] = config.utc_now_iso()
                result.update(u)
    stores.users.mutate(mutate)
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    audit_service.record_audit(admin["id"], "USER_UNLOCKED", user_id, "SUCCESS")
    return _public(result)


@router.get("/audit-logs")
def audit_logs(actor_id: str | None = None, action: str | None = None, limit: int = 200,
               user=Depends(AuditorOnly)):
    rows = stores.audit_logs.read()
    if actor_id:
        rows = [r for r in rows if r.get("actor_id") == actor_id]
    if action:
        rows = [r for r in rows if action.lower() in r.get("action", "").lower()]
    return sorted(rows, key=lambda r: r.get("timestamp", ""), reverse=True)[:limit]


@router.get("/security-events")
def security_events(limit: int = 200, user=Depends(AuditorOnly)):
    rows = stores.security_events.read()
    return sorted(rows, key=lambda r: r.get("timestamp", ""), reverse=True)[:limit]


@router.get("/system-health")
def system_health(admin=Depends(AdminOnly)):
    files = []
    data = config.data_dir()
    for filename in config.DATA_FILES:
        path = data / filename
        files.append({
            "file": filename,
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        })
    tb = ledger.trial_balance()
    reconciliation = compute_reconciliation()
    return {
        "status": "HEALTHY" if tb.balanced and reconciliation["all_balanced"] else "DEGRADED",
        "data_directory": str(data),
        "files": files,
        "ledger": {
            "entries": tb.entries_count,
            "accounts": tb.account_count,
            "total_debits_paise": tb.total_debits_paise,
            "total_credits_paise": tb.total_credits_paise,
            "difference_paise": tb.difference_paise,
            "balanced": tb.balanced,
        },
        "reconciliation": {
            "all_balanced": reconciliation["all_balanced"],
            "discrepancies": reconciliation["discrepancies"],
        },
        "active_sessions": len(stores.sessions.read()),
        "lock_directory": str(data / ".locks"),
    }
