"""Identity, authentication, MFA, lockout and server-side session management."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .. import config
from ..core.json_store import stores
from ..core.security import (
    decrypt_secret,
    digest_session_token,
    encrypt_secret,
    generate_recovery_codes,
    generate_totp_secret,
    hash_password,
    hash_recovery_code,
    new_id,
    new_session_token,
    needs_rehash,
    totp_provisioning_uri,
    verify_password,
    verify_totp,
)
from ..config import utc_now_iso
from .audit_service import notify, record_audit, record_security_event
from .ledger_service import ledger, LedgerError


ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "Customer": ["self.profile", "self.settings", "p2p.send", "p2p.receive", "qr.pay",
                 "beneficiaries.manage", "wallets.topup", "requests.create", "analytics.self"],
    "Merchant": ["self.profile", "self.settings", "p2p.send", "p2p.receive",
                 "beneficiaries.manage", "wallets.topup", "requests.create",
                 "merchant.dashboard", "analytics.self"],
    "Operator": ["self.profile", "self.settings", "ledger.read", "ledger.manual",
                 "ledger.reverse", "admin.users.read"],
    "Auditor": ["self.profile", "self.settings", "ledger.read", "audit.read", "security.read"],
    "Administrator": ["*"],
}


class AuthError(ValueError):
    pass


class StepUpRequired(AuthError):
    pass


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _public_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in user.items() if k not in (
        "password_hash", "mfa_secret_encrypted", "mfa_pending_secret_encrypted",
        "recovery_codes_encrypted",
    )}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def register(payload) -> Dict[str, Any]:
    data = payload.model_dump()
    users = stores.users.read()
    if any(u["username"].lower() == data["username"].lower() for u in users):
        raise AuthError("Username already registered")
    if any(u["email"].lower() == data["email"].lower() for u in users):
        raise AuthError("Email already registered")
    if any(u["phone"] == data["phone"] for u in users):
        raise AuthError("Phone already registered")

    uid = new_id("usr")
    stamp = utc_now_iso()
    user = {
        "id": uid,
        "username": data["username"],
        "email": data["email"],
        "phone": data["phone"],
        "full_name": data["full_name"],
        "role": data["role"],
        "password_hash": hash_password(data["password"]),
        "mfa_enabled": False,
        "mfa_secret_encrypted": None,
        "mfa_pending_secret_encrypted": None,
        "recovery_codes_encrypted": [],
        "vpa": f"{data['username']}@payflow",
        "is_active": True,
        "failed_login_attempts": 0,
        "locked_until": None,
        "created_at": stamp,
        "updated_at": stamp,
    }
    users.append(user)
    stores.users.write(users)

    account_id = f"acc_usr_{uid}_wallet"
    ledger.create_account_with_id(
        {
            "id": account_id,
            "code": f"WLT-{data['username'][:6].upper()}-{uid[-4:].upper()}",
            "name": f"{data['full_name']} Primary Wallet",
            "account_type": "Asset", "role": "Wallet", "user_id": uid,
            "allow_negative": False, "opening_balance_paise": 0,
            "active": True, "created_at": stamp,
        }
    )
    stores.wallets.append(
        {
            "id": new_id("wlt"), "user_id": uid, "account_id": account_id,
            "label": "Primary Wallet", "currency": "INR", "is_primary": True,
            "status": "ACTIVE", "created_at": stamp,
        }
    )
    stores.settings.append(
        {
            "user_id": uid, "theme": "dark", "currency_format": "INR",
            "daily_limit_paise": config.DEFAULT_DAILY_LIMIT_PAISE,
            "notifications": {"payments": True, "security": True, "product": False},
            "privacy": {"show_balance": True, "activity_visibility": "contacts"},
            "updated_at": stamp,
        }
    )
    notify(uid, "Welcome to PAYFLOW", "Your simulated wallet has been provisioned.")
    record_audit(uid, "USER_REGISTERED", "users", "SUCCESS", {"username": user["username"]})
    token = create_session(uid, mfa_verified=False)
    return {"user": _public_user(user), "token": token, "mfa_required": False}


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
def create_session(user_id: str, mfa_verified: bool = False) -> str:
    token = new_session_token()
    now = datetime.now(timezone.utc)
    record = {
        "token_hash": digest_session_token(token),
        "user_id": user_id,
        "created_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "last_seen_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "expires_at": (now + timedelta(hours=config.SESSION_SLIDING_HOURS)).isoformat(
            timespec="seconds").replace("+00:00", "Z"),
        "absolute_expires_at": (now + timedelta(days=config.SESSION_ABSOLUTE_DAYS)).isoformat(
            timespec="seconds").replace("+00:00", "Z"),
        "mfa_verified": bool(mfa_verified),
    }
    # Session rotation: invalidate all prior sessions on privilege elevation.
    def mutate(sessions):
        sessions[:] = [s for s in sessions if s.get("user_id") != user_id]
        sessions.append(record)
    stores.sessions.mutate(mutate)
    return token


def resolve_session(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    digest = digest_session_token(token)
    now = datetime.now(timezone.utc)
    result: Dict[str, Any] = {}

    def mutate(sessions):
        idx = next((i for i, s in enumerate(sessions) if s.get("token_hash") == digest), None)
        if idx is None:
            return
        session = sessions[idx]
        sliding = _parse(session.get("expires_at"))
        absolute = _parse(session.get("absolute_expires_at"))
        if (sliding is None or sliding < now) or (absolute is None or absolute < now):
            sessions.pop(idx)
            result["expired"] = True
            return
        session["last_seen_at"] = now.isoformat(timespec="seconds").replace("+00:00", "Z")
        session["expires_at"] = (now + timedelta(hours=config.SESSION_SLIDING_HOURS)).isoformat(
            timespec="seconds").replace("+00:00", "Z")
        result["session"] = dict(session)
        user = next((u for u in stores.users.read() if u["id"] == session["user_id"]), None)
        if not user or not user.get("is_active", True):
            sessions.pop(idx)
            result["invalid_user"] = True
            return
        result["user"] = dict(user)

    stores.sessions.mutate(mutate)
    if "user" not in result:
        return None
    return result


def rotate_session_mfa(user_id: str) -> str:
    """Re-issue a session with MFA verification flag set."""
    return create_session(user_id, mfa_verified=True)


def logout(token: Optional[str]) -> None:
    if not token:
        return
    digest = digest_session_token(token)
    stores.sessions.mutate(lambda s: s.__setitem__(slice(None), [x for x in s if x.get("token_hash") != digest]))


def active_sessions(user_id: str) -> List[Dict[str, Any]]:
    # The stored value is a SHA-256 digest (never the raw token), so it is safe
    # to return it: the UI needs it to display and revoke individual sessions.
    return [dict(s) for s in stores.sessions.read() if s.get("user_id") == user_id]


def revoke_session(user_id: str, token_hash: str) -> None:
    stores.sessions.mutate(
        lambda s: s.__setitem__(slice(None), [x for x in s if not (x.get("user_id") == user_id and x.get("token_hash") == token_hash)])
    )


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
def login(payload, ip: Optional[str] = None) -> Dict[str, Any]:
    data = payload.model_dump()
    username = data.get("username", "")
    users = stores.users.read()
    user = next(
        (u for u in users if u["username"].lower() == username.lower() or u["email"].lower() == username.lower()),
        None,
    )
    if user is None:
        record_security_event("LOGIN_FAILURE", username, "UNKNOWN_USER", ip=ip)
        raise AuthError("Invalid credentials")

    locked = _parse(user.get("locked_until"))
    if locked and locked > datetime.now(timezone.utc):
        record_security_event("LOGIN_BLOCKED", username, "ACCOUNT_LOCKED", ip=ip)
        raise AuthError("Account temporarily locked due to repeated failed logins")

    if not verify_password(user["password_hash"], data.get("password", "")):
        def bump(users_list):
            for u in users_list:
                if u["id"] == user["id"]:
                    u["failed_login_attempts"] = u.get("failed_login_attempts", 0) + 1
                    if u["failed_login_attempts"] >= config.MAX_FAILED_LOGIN_ATTEMPTS:
                        until = datetime.now(timezone.utc) + timedelta(minutes=config.LOCKOUT_MINUTES)
                        u["locked_until"] = until.isoformat(timespec="seconds").replace("+00:00", "Z")
                        record_security_event("ACCOUNT_LOCKOUT", username, "LOCKED", ip=ip)
                    u["updated_at"] = utc_now_iso()
        stores.users.mutate(bump)
        record_security_event("LOGIN_FAILURE", username, "BAD_PASSWORD", ip=ip)
        raise AuthError("Invalid credentials")

    if needs_rehash(user["password_hash"]):
        stores.users.mutate(
            lambda ul: [u.update({"password_hash": hash_password(data["password"]),
                                  "updated_at": utc_now_iso()}) for u in ul if u["id"] == user["id"]]
        )

    if user.get("mfa_enabled"):
        code = data.get("totp_code")
        recovery = data.get("recovery_code")
        if not code and not recovery:
            return {"mfa_required": True, "user_id": user["id"]}
        if code and not verify_totp(decrypt_secret(user["mfa_secret_encrypted"]), code):
            record_security_event("MFA_FAILURE", username, "BAD_TOTP", ip=ip)
            raise AuthError("Invalid TOTP code")
        if recovery:
            hashed = hash_recovery_code(recovery)
            def consume(ul):
                for u in ul:
                    if u["id"] == user["id"]:
                        if hashed not in u.get("recovery_codes_encrypted", []):
                            raise AuthError("Invalid recovery code")
                        u["recovery_codes_encrypted"].remove(hashed)
            stores.users.mutate(consume)
            record_audit(user["id"], "MFA_RECOVERY_USED", "auth", "SUCCESS", ip=ip)

    def reset(ul):
        for u in ul:
            if u["id"] == user["id"]:
                u["failed_login_attempts"] = 0
                u["locked_until"] = None
                u["updated_at"] = utc_now_iso()
    stores.users.mutate(reset)
    record_audit(user["id"], "LOGIN", "auth", "SUCCESS", ip=ip)
    token = create_session(user["id"], mfa_verified=bool(user.get("mfa_enabled")))
    return {
        "mfa_required": False,
        "token": token,
        "user": _public_user(next(u for u in stores.users.read() if u["id"] == user["id"])),
    }


# ---------------------------------------------------------------------------
# MFA setup
# ---------------------------------------------------------------------------
def setup_mfa(user_id: str) -> Dict[str, Any]:
    secret = generate_totp_secret()
    codes, digests = generate_recovery_codes()

    def mutate(ul):
        for u in ul:
            if u["id"] == user_id:
                u["mfa_pending_secret_encrypted"] = encrypt_secret(secret)
                u["recovery_codes_encrypted"] = digests
    stores.users.mutate(mutate)
    user = next(u for u in stores.users.read() if u["id"] == user_id)
    uri = totp_provisioning_uri(secret, user["email"])
    record_audit(user_id, "MFA_SETUP_INITIATED", "auth", "SUCCESS")
    return {
        "secret": secret,
        "provisioning_uri": uri,
        "otpauth_url": uri,
        "recovery_codes": codes,
    }


def verify_mfa_setup(user_id: str, code: str) -> Dict[str, Any]:
    user = next(u for u in stores.users.read() if u["id"] == user_id)
    pending = user.get("mfa_pending_secret_encrypted")
    if not pending:
        raise AuthError("No pending MFA setup")
    if not verify_totp(decrypt_secret(pending), code):
        raise AuthError("Invalid verification code")

    def mutate(ul):
        for u in ul:
            if u["id"] == user_id:
                u["mfa_secret_encrypted"] = pending
                u["mfa_pending_secret_encrypted"] = None
                u["mfa_enabled"] = True
                u["updated_at"] = utc_now_iso()
    stores.users.mutate(mutate)
    record_audit(user_id, "MFA_ENABLED", "auth", "SUCCESS")
    return {"mfa_enabled": True}


def disable_mfa(user_id: str, code: str) -> Dict[str, Any]:
    user = next(u for u in stores.users.read() if u["id"] == user_id)
    if not user.get("mfa_enabled"):
        raise AuthError("MFA is not enabled")
    if not verify_totp(decrypt_secret(user["mfa_secret_encrypted"]), code):
        raise AuthError("Invalid verification code")

    def mutate(ul):
        for u in ul:
            if u["id"] == user_id:
                u["mfa_enabled"] = False
                u["mfa_secret_encrypted"] = None
                u["recovery_codes_encrypted"] = []
                u["updated_at"] = utc_now_iso()
    stores.users.mutate(mutate)
    record_audit(user_id, "MFA_DISABLED", "auth", "SUCCESS")
    return {"mfa_enabled": False}


def change_password(user_id: str, current: str, new: str) -> None:
    user = next(u for u in stores.users.read() if u["id"] == user_id)
    if not verify_password(user["password_hash"], current):
        raise AuthError("Current password is incorrect")
    def mutate(ul):
        for u in ul:
            if u["id"] == user_id:
                u["password_hash"] = hash_password(new)
                u["updated_at"] = utc_now_iso()
    stores.users.mutate(mutate)
    record_security_event("PASSWORD_CHANGED", user_id, "SUCCESS")


def assert_step_up(session: Dict[str, Any], amount_paise: int, totp_code: Optional[str], user: Dict[str, Any]) -> bool:
    """Return True if step-up is satisfied; raise StepUpRequired otherwise."""
    if amount_paise <= config.MFA_STEP_UP_PAISE:
        return False
    if session.get("mfa_verified") and totp_code is None:
        return True
    if totp_code and user.get("mfa_enabled") and verify_totp(decrypt_secret(user["mfa_secret_encrypted"]), totp_code):
        return True
    raise StepUpRequired("Amount exceeds Rs. 10,000 - TOTP step-up verification required")


def permissions_for(role: str) -> List[str]:
    if role == "Administrator":
        return ["*"]
    return ROLE_PERMISSIONS.get(role, [])
