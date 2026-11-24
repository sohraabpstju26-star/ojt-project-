"""PAYFLOW FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .api.routers import (
    admin, analytics, auth, beneficiaries, bills, ledger, payments, requests, user, wallets,
)
from .core.bootstrap import ensure_initialized
from .services.ledger_service import LedgerError, ledger as ledger_engine


FRONTEND = config.PROJECT_ROOT / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_initialized()
    yield


app = FastAPI(
    title="PAYFLOW API",
    version="1.0.0",
    description="Unified digital payments & immutable double-entry financial ledger (simulation).",
    lifespan=lifespan,
)


@app.exception_handler(LedgerError)
async def ledger_error_handler(request: Request, exc: LedgerError):
    return JSONResponse(status_code=400, content={"detail": str(exc), "error": "LEDGER_INVARIANT"})


for router in (
    auth.router, wallets.router, payments.router, requests.router,
    beneficiaries.router, bills.router, ledger.router, analytics.router,
    admin.router, user.router,
):
    app.include_router(router)


@app.get("/api/health", tags=["System"])
def health():
    tb = ledger_engine.trial_balance()
    return {"status": "OK", "ledger_balanced": tb.balanced, "difference_paise": tb.difference_paise}


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
if (FRONTEND / "css").exists():
    app.mount("/css", StaticFiles(directory=str(FRONTEND / "css")), name="css")
if (FRONTEND / "js").exists():
    app.mount("/js", StaticFiles(directory=str(FRONTEND / "js")), name="js")


@app.get("/", include_in_schema=False)
def landing():
    return FileResponse(str(FRONTEND / "landing.html"))


@app.get("/landing.html", include_in_schema=False)
def landing_page():
    return FileResponse(str(FRONTEND / "landing.html"))


@app.get("/app", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def index_html():
    return FileResponse(str(FRONTEND / "index.html"))


@app.get("/login.html", include_in_schema=False)
def login_page():
    return FileResponse(str(FRONTEND / "login.html"))


@app.get("/register.html", include_in_schema=False)
def register_page():
    return FileResponse(str(FRONTEND / "register.html"))
