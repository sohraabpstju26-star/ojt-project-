"""Argon2id, TOTP, encryption-at-rest, lockout and session lifecycle."""
from __future__ import annotations

import json

import pyotp

from backend.app.core.security import (
    decrypt_secret, encrypt_secret, hash_password, verify_password,
)


def test_argon2id_password_hashing():
    hashed = hash_password("PayflowTest@123")
    assert hashed.startswith("$argon2id$v=19$m=65536,t=3,p=1$")
    assert verify_password(hashed, "PayflowTest@123") is True
    assert verify_password(hashed, "wrong-password") is False
    assert hashed != hash_password("PayflowTest@123")  # unique salts


def test_totp_generation_and_validation():
    secret = pyotp.random_base32(length=32)
    assert len(secret) == 32
    assert verify_totp_local(secret, pyotp.TOTP(secret).now()) is True
    assert verify_totp_local(secret, "000000") is False


def verify_totp_local(secret, code):
    from backend.app.core.security import verify_totp
    return verify_totp(secret, code)


def test_aes_gcm_encryption_at_rest(env):
    token = encrypt_secret("JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP")
    assert token.startswith("enc_aes256_gcm_")
    assert "JBSWY3DPEHPK3PXP" not in token
    assert decrypt_secret(token) == "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


def test_account_lockout_after_five_failures(client):
    for _ in range(5):
        response = client.post(
            "/api/auth/login", json={"username": "aditi_sharma", "password": "wrong"}
        )
        assert response.status_code == 401
    response = client.post(
        "/api/auth/login", json={"username": "aditi_sharma", "password": "Customer@123"}
    )
    assert response.status_code == 401
    assert "locked" in response.json()["detail"].lower()


def test_session_rotation_and_revocation(client, env):
    first = client.post(
        "/api/auth/login", json={"username": "aditi_sharma", "password": "Customer@123"}
    )
    assert first.status_code == 200
    sessions = json.loads((env / "sessions.json").read_text())
    assert len([s for s in sessions if s["user_id"] == first.json()["user"]["id"]]) == 1

    second = client.post(
        "/api/auth/login", json={"username": "aditi_sharma", "password": "Customer@123"}
    )
    assert second.status_code == 200
    sessions = json.loads((env / "sessions.json").read_text())
    assert len([s for s in sessions if s["user_id"] == second.json()["user"]["id"]]) == 1
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/session").status_code == 401


def test_mfa_setup_verify_and_step_up(client, env):
    client.post("/api/auth/login", json={"username": "aditi_sharma", "password": "Customer@123"})
    setup = client.post("/api/auth/mfa/setup")
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert len(secret) == 32
    assert len(setup.json()["recovery_codes"]) == 8

    raw_users = (env / "users.json").read_text()
    assert secret not in raw_users  # never plaintext on disk

    verified = client.post("/api/auth/mfa/verify", json={"code": pyotp.TOTP(secret).now()})
    assert verified.status_code == 200
    raw_users = (env / "users.json").read_text()
    assert "enc_aes256_gcm_" in raw_users

    assert client.post("/api/auth/logout").status_code == 200
    challenge = client.post(
        "/api/auth/login", json={"username": "aditi_sharma", "password": "Customer@123"}
    )
    assert challenge.json().get("mfa_required") is True
    complete = client.post(
        "/api/auth/login",
        json={"username": "aditi_sharma", "password": "Customer@123",
              "totp_code": pyotp.TOTP(secret).now()},
    )
    assert complete.status_code == 200
