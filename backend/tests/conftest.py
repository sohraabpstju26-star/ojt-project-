"""Shared Pytest fixtures - each test gets an isolated, freshly seeded data dir."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def env(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("PAYFLOW_DATA_DIR", str(data_dir))
    from backend.app.core.bootstrap import ensure_initialized
    ensure_initialized(force=True)
    return data_dir


@pytest.fixture
def client(env):
    from backend.app.main import app
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def login(client):
    def _login(username: str, password: str):
        response = client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        assert response.status_code == 200, response.text
        return response.json()["user"]
    return _login


@pytest.fixture
def customer(client, login):
    return login("aditi_sharma", "Customer@123")


@pytest.fixture
def operator(client, login):
    return login("operator", "Oper@12345")
