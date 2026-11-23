"""Server-side financial analytics: Pandas aggregation + headless Matplotlib SVG charts."""
from __future__ import annotations

import base64
import io
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from ..config import utc_now_iso
from ..core.json_store import stores
from .ledger_service import ledger

plt.rcParams.update({
    "figure.facecolor": "#111827",
    "axes.facecolor": "#162032",
    "axes.edgecolor": "#1e293b",
    "axes.labelcolor": "#94a3b8",
    "xtick.color": "#94a3b8",
    "ytick.color": "#94a3b8",
    "text.color": "#f8fafc",
    "grid.color": "#1e293b",
    "font.size": 10,
    "axes.titlesize": 12,
})

CATEGORY_COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444", "#06b6d4", "#ec4899", "#84cc16"]


def _lines_df() -> pd.DataFrame:
    rows = []
    for entry in stores.entries.read():
        for line in entry.get("lines", []):
            rows.append({
                "date": entry.get("date", ""),
                "month": entry.get("date", "")[:7],
                "timestamp": entry.get("timestamp", ""),
                "transaction_id": entry.get("transaction_id", ""),
                "category": entry.get("category", "Other"),
                "account_id": line.get("account_id", ""),
                "debit_paise": int(line.get("debit_paise", 0)),
                "credit_paise": int(line.get("credit_paise", 0)),
                "total_paise": int(entry.get("total_paise", 0)),
            })
    if not rows:
        return pd.DataFrame(columns=["date", "month", "timestamp", "transaction_id", "category",
                                     "account_id", "debit_paise", "credit_paise", "total_paise"])
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def _user_accounts(user_id: str) -> set[str]:
    return {w["account_id"] for w in stores.wallets.read() if w.get("user_id") == user_id}


def _inr(paise: int) -> str:
    return f"Rs. {paise / 100:,.2f}"


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def dashboard(user_id: Optional[str], is_privileged: bool) -> Dict[str, Any]:
    df = _lines_df()
    from . import wallet_service
    if user_id:
        accounts = _user_accounts(user_id)
        relevant = df[df["account_id"].isin(accounts)] if not df.empty else df
        wallets = wallet_service.list_wallets(user_id)
        total_balance = sum(w["balance_paise"] for w in wallets)
        wallet_count = len(wallets)
    else:
        relevant = df
        balances = ledger.calculate_balances()
        total_balance = sum(balances.values())
        wallet_count = sum(1 for a in stores.accounts.read() if a.get("role") == "Wallet")

    if relevant.empty:
        inflow = outflow = monthly_spend = 0
        txn_ids = []
    else:
        inflow = int(relevant["debit_paise"].sum())
        outflow = int(relevant["credit_paise"].sum())
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        monthly_spend = int(relevant[(relevant["month"] == current_month)]["credit_paise"].sum())
        txn_ids = relevant["transaction_id"].unique().tolist()

    history = ledger.get_transaction_history()
    if user_id:
        history = [e for e in history if any(l["account_id"] in _user_accounts(user_id) for l in e["lines"])]
    recent = []
    for entry in history[:6]:
        meta = entry.get("metadata", {})
        recent.append({
            "transaction_id": entry["transaction_id"],
            "description": entry["description"],
            "category": entry["category"],
            "amount_paise": entry["total_paise"],
            "timestamp": entry["timestamp"],
            "counterparty": meta.get("receiver_vpa") or meta.get("sender_vpa") or "PAYFLOW",
        })
    return {
        "total_balance_paise": int(total_balance),
        "inflow_paise": int(inflow),
        "outflow_paise": int(outflow),
        "transaction_count": len(txn_ids),
        "wallet_count": int(wallet_count),
        "monthly_spend_paise": int(monthly_spend),
        "recent_transactions": recent,
    }


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------
def _svg(fig) -> str:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="svg", bbox_inches="tight", facecolor="#111827")
    plt.close(fig)
    return "data:image/svg+xml;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _month_labels(n: int) -> List[str]:
    today = datetime.now(timezone.utc)
    labels = []
    for i in range(n - 1, -1, -1):
        d = today - timedelta(days=30 * i)
        labels.append(d.strftime("%Y-%m"))
    return labels


def cashflow_chart(user_id: Optional[str] = None, months: int = 6) -> Dict[str, Any]:
    df = _lines_df()
    if user_id and not df.empty:
        df = df[df["account_id"].isin(_user_accounts(user_id))]
    labels = _month_labels(months)
    inflow = [int(df[(df["month"] == m)]["debit_paise"].sum()) / 100 if not df.empty else 0 for m in labels]
    outflow = [int(df[(df["month"] == m)]["credit_paise"].sum()) / 100 if not df.empty else 0 for m in labels]
    cumulative_in, cumulative_out, run_in, run_out = [], [], 0, 0
    for a, b in zip(inflow, outflow):
        run_in += a
        run_out += b
        cumulative_in.append(run_in)
        cumulative_out.append(run_out)

    fig, ax = plt.subplots(figsize=(9, 4.2))
    short = [datetime.strptime(m, "%Y-%m").strftime("%b %y") for m in labels]
    ax.plot(short, cumulative_in, color="#10b981", marker="o", linewidth=2.5, label="Money received")
    ax.plot(short, cumulative_out, color="#ef4444", marker="o", linewidth=2.5, label="Money spent")
    ax.fill_between(short, cumulative_in, alpha=0.10, color="#10b981")
    ax.fill_between(short, cumulative_out, alpha=0.10, color="#ef4444")
    ax.set_title("Cumulative Cash Flow Trend")
    ax.set_ylabel("Amount (INR)")
    ax.grid(True, alpha=0.35)
    ax.legend(frameon=False)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return {
        "format": "svg", "image": _svg(fig), "title": "Monthly Cash Flow Trend",
        "summary": {
            "months": months,
            "total_received_paise": int(sum(inflow) * 100),
            "total_spent_paise": int(sum(outflow) * 100),
        },
    }


def categories_chart(user_id: Optional[str] = None) -> Dict[str, Any]:
    df = _lines_df()
    if user_id and not df.empty:
        df = df[df["account_id"].isin(_user_accounts(user_id))]
    if df.empty:
        grouped = pd.Series(dtype="int64")
    else:
        spend = df[df["credit_paise"] > 0]
        grouped = spend.groupby("category")["credit_paise"].sum().sort_values(ascending=False)

    fig, ax = plt.subplots(figsize=(7.2, 5))
    if grouped.empty:
        ax.text(0.5, 0.5, "No spending data available", ha="center", va="center", color="#64748b")
        ax.axis("off")
    else:
        values = [int(v) / 100 for v in grouped.values]
        wedges, texts, autotexts = ax.pie(
            values, labels=None, autopct=lambda p: f"{p:.1f}%",
            startangle=140, colors=CATEGORY_COLORS[:len(values)],
            wedgeprops=dict(width=0.42, edgecolor="#111827", linewidth=2),
            pctdistance=0.78,
        )
        for t in autotexts:
            t.set_color("#f8fafc")
            t.set_fontsize(9)
        ax.legend(wedges, [str(x) for x in grouped.index], loc="center left",
                  bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=9)
        ax.text(0, 0, _inr(int(grouped.sum())), ha="center", va="center",
                fontsize=11, color="#f8fafc", fontweight="bold")
    ax.set_title("Spending Distribution by Category")
    fig.tight_layout()
    return {
        "format": "svg", "image": _svg(fig), "title": "Category Breakdown",
        "summary": {str(k): int(v) for k, v in grouped.items()},
    }


def velocity_chart(user_id: Optional[str] = None, days: int = 14) -> Dict[str, Any]:
    df = _lines_df()
    if user_id and not df.empty:
        df = df[df["account_id"].isin(_user_accounts(user_id))]
    labels = [(datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days - 1, -1, -1)]
    counts, volumes = [], []
    for d in labels:
        day = df[df["date"] == pd.Timestamp(d)] if not df.empty else df
        txns = day["transaction_id"].nunique() if not day.empty else 0
        vol = int(day.drop_duplicates("transaction_id")["total_paise"].sum()) / 100 if not day.empty else 0
        counts.append(txns)
        volumes.append(vol)

    fig, ax1 = plt.subplots(figsize=(9, 4))
    short = [d[5:] for d in labels]
    ax1.bar(short, volumes, color="#3b82f6", alpha=0.75, label="Volume (INR)")
    ax1.set_ylabel("Volume (INR)", color="#3b82f6")
    ax1.tick_params(axis="x", rotation=45)
    ax2 = ax1.twinx()
    ax2.plot(short, counts, color="#f59e0b", marker="o", linewidth=2, label="Transaction count")
    ax2.set_ylabel("Transactions", color="#f59e0b")
    ax1.set_title("Transaction Velocity & Volume")
    ax1.grid(True, alpha=0.25)
    fig.tight_layout()
    return {
        "format": "svg", "image": _svg(fig), "title": "Transaction Velocity & Volume",
        "summary": {"days": days, "total_transactions": int(sum(counts)),
                    "total_volume_paise": int(sum(volumes) * 100)},
    }


def status_chart() -> Dict[str, Any]:
    requests = stores.requests.read()
    completed = sum(1 for e in stores.entries.read() if not e.get("is_reversal"))
    pending = sum(1 for r in requests if r.get("status") == "PENDING")
    rejected = sum(1 for r in requests if r.get("status") in ("REJECTED", "CANCELLED", "EXPIRED"))
    sizes = [completed, pending, rejected]
    labels = ["Completed", "Pending", "Rejected / Cancelled"]
    colors = ["#10b981", "#f59e0b", "#ef4444"]

    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    if sum(sizes) == 0:
        ax.text(0.5, 0.5, "No activity yet", ha="center", color="#64748b")
        ax.axis("off")
    else:
        ax.pie(sizes, labels=labels, colors=colors, autopct="%1.1f%%", startangle=120,
               wedgeprops=dict(edgecolor="#111827", linewidth=2))
    ax.set_title("Success vs Failure Ratio")
    fig.tight_layout()
    return {
        "format": "svg", "image": _svg(fig), "title": "Success vs Failure Ratios",
        "summary": {"completed": completed, "pending": pending, "rejected": rejected},
    }


def reconciliation() -> Dict[str, Any]:
    accounts = stores.accounts.read()
    entries = stores.entries.read()
    cached = stores.balances.read()
    movements: Dict[str, Dict[str, int]] = {}
    for entry in entries:
        for line in entry.get("lines", []):
            row = movements.setdefault(line["account_id"], {"debits": 0, "credits": 0})
            row["debits"] += int(line.get("debit_paise", 0))
            row["credits"] += int(line.get("credit_paise", 0))
    rows = []
    discrepancies = 0
    for account in accounts:
        aid = account["id"]
        debits = movements.get(aid, {}).get("debits", 0)
        credits = movements.get(aid, {}).get("credits", 0)
        opening = int(account.get("opening_balance_paise", 0))
        expected = opening + debits - credits if account["account_type"] in ("Asset", "Expense") \
            else opening + credits - debits
        actual = int(cached.get(aid, opening))
        difference = expected - actual
        if difference != 0:
            discrepancies += 1
        rows.append({
            "account_id": aid, "code": account["code"], "name": account["name"],
            "account_type": account["account_type"], "opening_balance_paise": opening,
            "debits_paise": debits, "credits_paise": credits,
            "expected_balance_paise": expected, "cached_balance_paise": actual,
            "difference_paise": difference,
            "status": "BALANCED" if difference == 0 else "DISCREPANCY",
        })
    return {
        "generated_at": utc_now_iso(), "rows": rows,
        "all_balanced": discrepancies == 0, "discrepancies": discrepancies,
    }
