"""Cryptographic primitives: Argon2id, TOTP, AES-256-GCM, session digests."""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from typing import List, Tuple

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .. import config

_ph = PasswordHasher(
    memory_cost=config.PASSWORD_MEMORY_COST_KIB,
    time_cost=config.PASSWORD_TIME_COST,
    parallelism=config.PASSWORD_PARALLELISM,
    hash_len=32,
    salt_len=config.PASSWORD_SALT_BYTES,
)
AES_PREFIX = "enc_aes256_gcm_"
_key_cache: dict[str, bytes] = {}


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return bool(_ph.verify(password_hash, password))
    except (VerifyMismatchError, VerificationError, InvalidHashError, ValueError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _ph.check_needs_rehash(password_hash)
    except Exception:
        return True


# ---------------------------------------------------------------------------
# AES-256-GCM secret encryption at rest
# ---------------------------------------------------------------------------
def get_aes_key() -> bytes:
    key_path = config.secrets_dir() / "app_secret.key"
    cache_key = str(key_path)
    if cache_key in _key_cache:
        return _key_cache[cache_key]
    if key_path.exists():
        key = key_path.read_bytes()
        if len(key) != 32:
            raise RuntimeError("app_secret.key is corrupt (expected 32 bytes)")
    else:
        key = os.urandom(32)
        fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, key)
            os.fsync(fd)
        finally:
            os.close(fd)
    _key_cache[cache_key] = key
    return key


def encrypt_secret(plaintext: str) -> str:
    nonce = os.urandom(12)
    ct = AESGCM(get_aes_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return AES_PREFIX + base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def decrypt_secret(token: str) -> str:
    if not token.startswith(AES_PREFIX):
        raise ValueError("Unsupported secret envelope")
    raw = base64.urlsafe_b64decode(token[len(AES_PREFIX):].encode("ascii"))
    return AESGCM(get_aes_key()).decrypt(raw[:12], raw[12:], None).decode("utf-8")


# ---------------------------------------------------------------------------
# TOTP MFA (RFC 6238)
# ---------------------------------------------------------------------------
def generate_totp_secret() -> str:
    return pyotp.random_base32(length=32)


def totp_provisioning_uri(secret: str, account_name: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name="PAYFLOW")


def verify_totp(secret: str, code: str, valid_window: int = 1) -> bool:
    if not secret or not code:
        return False
    try:
        return pyotp.TOTP(secret).verify(str(code).strip(), valid_window=valid_window)
    except Exception:
        return False


def generate_recovery_codes(count: int = 8) -> Tuple[List[str], List[str]]:
    """Return (plaintext codes, SHA-256 digests) - plaintext shown only once."""
    codes = [secrets.token_hex(4) for _ in range(count)]
    digests = [hashlib.sha256(c.encode()).hexdigest() for c in codes]
    return codes, digests


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode()).hexdigest()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def digest_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def new_transaction_id() -> str:
    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"TXN_{stamp}{secrets.token_hex(2).upper()}"
