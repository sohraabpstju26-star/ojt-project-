"""Append-only operational audit and security event recording."""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..config import utc_now_iso
from ..core.security import new_id
from ..core.json_store import stores


def record_audit(
    actor_id: Optional[str],
    action: str,
    resource: str,
    outcome: str = "SUCCESS",
    detail: Optional[Dict[str, Any]] = None,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    event = {
        "id": new_id("aud"),
        "timestamp": utc_now_iso(),
        "actor_id": actor_id,
        "action": action,
        "resource": resource,
        "outcome": outcome,
        "detail": detail or {},
        "ip_address": ip,
    }
    stores.audit_logs.append(event)
    return event


def record_security_event(
    event_type: str,
    actor: Optional[str],
    outcome: str,
    detail: Optional[Dict[str, Any]] = None,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    event = {
        "id": new_id("sec"),
        "timestamp": utc_now_iso(),
        "event_type": event_type,
        "actor": actor,
        "outcome": outcome,
        "detail": detail or {},
        "ip_address": ip,
    }
    stores.security_events.append(event)
    return event


def notify(
    user_id: str,
    title: str,
    message: str,
    kind: str = "system",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    note = {
        "id": new_id("ntf"),
        "user_id": user_id,
        "type": kind,
        "title": title,
        "message": message,
        "read": False,
        "metadata": metadata or {},
        "created_at": utc_now_iso(),
    }
    stores.notifications.append(note)
    return note
