"""Role-based access control is enforced server-side on every endpoint group."""
from __future__ import annotations


def test_customer_blocked_from_admin_and_auditor_routes(client, customer):
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/admin/audit-logs").status_code == 403
    assert client.get("/api/ledger/trial-balance").status_code == 403
    assert client.post("/api/ledger/entries", json={}).status_code == 403


def test_auditor_has_read_only_ledger_access(client, login):
    login("auditor", "Audit@12345")
    assert client.get("/api/ledger/accounts").status_code == 200
    assert client.get("/api/ledger/entries").status_code == 200
    assert client.get("/api/ledger/trial-balance").status_code == 200
    assert client.get("/api/admin/audit-logs").status_code == 200
    assert client.post("/api/ledger/entries", json={}).status_code == 403
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/admin/system-health").status_code == 403


def test_operator_can_reverse_but_not_change_roles(client, operator):
    tb = client.get("/api/ledger/trial-balance")
    assert tb.status_code == 200
    assert tb.json()["balanced"] is True

    from backend.app.core.json_store import stores
    entry = next(e for e in stores.entries.read() if e["category"] == "P2P Transfer")
    user = next(u for u in stores.users.read() if u["username"] == "aditi_sharma")
    assert client.post(f"/api/ledger/reverse/{entry['transaction_id']}",
                       json={"reason": "Test reversal"}).status_code == 200
    assert client.put(f"/api/admin/users/{user['id']}/role",
                      json={"role": "Administrator"}).status_code == 403


def test_operator_denied_audit_logs(client, operator):
    assert client.get("/api/admin/audit-logs").status_code == 403
    assert client.get("/api/admin/security-events").status_code == 403


def test_admin_full_access(client, login):
    login("admin", "Admin@12345")
    assert client.get("/api/admin/users").status_code == 200
    assert client.get("/api/admin/audit-logs").status_code == 200
    assert client.get("/api/admin/system-health").status_code == 200
    assert client.get("/api/ledger/trial-balance").status_code == 200
