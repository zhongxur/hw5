"""Campus Customs desk API (FastAPI).

Start from backend/:  uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import config  # noqa: F401  (loads .env, puts mcp_server on sys.path)
import events
import shop_db as db
import team
from config import OUTPUT
from models import ROLE_LABELS, ApproveBody

RUNS_DIR = OUTPUT / "runs"
_running: dict[int, asyncio.Task] = {}
_summaries: dict[int, dict[str, Any]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # one MCP server process for the whole backend; all agents share it
    async with team.mcp_toolset():
        yield


app = FastAPI(title="Campus Customs Desk", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_summary(ticket_id: int) -> dict[str, Any] | None:
    if ticket_id in _summaries:
        return _summaries[ticket_id]
    p = RUNS_DIR / f"ticket_{ticket_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "model": config.MODEL_NAME, "db": db.DB_PATH.name}


@app.get("/api/tickets")
def tickets() -> list[dict[str, Any]]:
    """The three desk tickets with status (open / in_progress / awaiting_approval / resolved)."""
    out = []
    for t in db.list_tickets():
        t["running"] = t["id"] in _running and not _running[t["id"]].done()
        t["pending_count"] = len(db.list_pending_actions(t["id"], status="pending"))
        out.append(t)
    return out


@app.get("/api/tickets/{ticket_id}")
def ticket_detail(ticket_id: int) -> dict[str, Any]:
    t = db.get_ticket(ticket_id)
    if not t:
        raise HTTPException(404, f"ticket {ticket_id} not found")
    return {
        "ticket": t,
        "running": ticket_id in _running and not _running[ticket_id].done(),
        "pending_actions": db.list_pending_actions(ticket_id),
        "customer_messages": db.list_customer_messages(ticket_id),
        "summary": _load_summary(ticket_id),
    }


@app.post("/api/tickets/{ticket_id}/run")
async def run_ticket(ticket_id: int) -> dict[str, Any]:
    """Start the agent team on one ticket (runs in the background; poll /api/events)."""
    if not db.get_ticket(ticket_id):
        raise HTTPException(404, f"ticket {ticket_id} not found")
    if ticket_id in _running and not _running[ticket_id].done():
        raise HTTPException(409, f"ticket {ticket_id} is already running")

    async def _go() -> None:
        summary = await team.run_ticket(ticket_id)
        _summaries[ticket_id] = summary
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        (RUNS_DIR / f"ticket_{ticket_id}.json").write_text(json.dumps(summary, indent=2, default=str))

    _running[ticket_id] = asyncio.create_task(_go())
    return {"started": True, "ticket_id": ticket_id}


@app.get("/api/events")
def get_events(since: int = 0, ticket_id: int | None = None) -> list[dict[str, Any]]:
    """Recent agent events (what each agent said, tool calls and results) after seq `since`."""
    return [e.model_dump() for e in events.recent(since, ticket_id)]


@app.get("/api/approvals")
def approvals(status: str | None = "pending") -> list[dict[str, Any]]:
    """Payments, purchases and price overrides prepared by agents."""
    return db.list_pending_actions(status=status or None)


@app.post("/api/approvals/{action_id}/approve")
def approve(action_id: int, body: ApproveBody | None = None) -> dict[str, Any]:
    """HUMAN ONLY: approve a prepared pay / purchase / override. The only route that moves cash."""
    approver = (body.approver if body else "store manager").strip() or "store manager"
    result = db.decide_action(action_id, approve=True, approver=approver)
    if "error" in result:
        raise HTTPException(400, result["error"])
    a = next(x for x in db.list_pending_actions() if x["id"] == action_id)
    events.emit("human", a["ticket_id"], "human", 0, 0, "human", tool="approve",
                args={"action_id": action_id, "approver": approver},
                text=f"{approver} approved #{action_id}: {a['description']}")
    return result


@app.post("/api/approvals/{action_id}/reject")
def reject(action_id: int, body: ApproveBody | None = None) -> dict[str, Any]:
    approver = (body.approver if body else "store manager").strip() or "store manager"
    result = db.decide_action(action_id, approve=False, approver=approver)
    if "error" in result:
        raise HTTPException(400, result["error"])
    a = next(x for x in db.list_pending_actions() if x["id"] == action_id)
    events.emit("human", a["ticket_id"], "human", 0, 0, "human", tool="reject",
                args={"action_id": action_id, "approver": approver},
                text=f"{approver} rejected #{action_id}: {a['description']}")
    return result


@app.get("/api/cash")
def cash() -> dict[str, Any]:
    """Current checking balance from cash_accounts, plus commitments and payments made."""
    pos = db.get_cash_position()
    pos["payments"] = db.list_payments()
    return pos


@app.post("/api/reset")
def reset() -> dict[str, Any]:
    """Copy data/campus_customs.db over the working copy for a clean run."""
    if any(not t.done() for t in _running.values()):
        raise HTTPException(409, "a ticket is still running")
    result = db.reset_database()
    _summaries.clear()
    for p in RUNS_DIR.glob("ticket_*.json"):
        p.unlink()
    events.clear_feed()
    events.emit("human", 0, "human", 0, 0, "human", tool="reset",
                text=f"Database reset — checking ${result['checking_balance']:,.2f}")
    return result


@app.get("/api/agents")
def agents() -> list[dict[str, Any]]:
    return [{"role": r, "label": ROLE_LABELS[r], "tools": sorted(team.ROLE_TOOLS[r])}
            for r in ROLE_LABELS]
