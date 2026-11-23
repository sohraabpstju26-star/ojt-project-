"""Analytics endpoints: /api/analytics (server-side Pandas + Matplotlib)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...models.schemas import ChartOut, DashboardOut, ReconciliationOut
from ...services import analytics_service
from ..deps import get_current_user

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


def _scope(user: dict) -> str | None:
    return None if user["role"] in ("Operator", "Auditor", "Administrator") else user["id"]


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(user=Depends(get_current_user)):
    return analytics_service.dashboard(_scope(user), user["role"] in ("Operator", "Auditor", "Administrator"))


@router.get("/chart/cashflow", response_model=ChartOut)
def cashflow(months: int = Query(default=6, ge=3, le=12), user=Depends(get_current_user)):
    return analytics_service.cashflow_chart(_scope(user), months)


@router.get("/chart/categories", response_model=ChartOut)
def categories(user=Depends(get_current_user)):
    return analytics_service.categories_chart(_scope(user))


@router.get("/chart/velocity", response_model=ChartOut)
def velocity(days: int = Query(default=14, ge=7, le=30), user=Depends(get_current_user)):
    return analytics_service.velocity_chart(_scope(user), days)


@router.get("/chart/status", response_model=ChartOut)
def status(user=Depends(get_current_user)):
    return analytics_service.status_chart()


@router.get("/reconciliation", response_model=ReconciliationOut)
def reconciliation(user=Depends(get_current_user)):
    return analytics_service.reconciliation()
