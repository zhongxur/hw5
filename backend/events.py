"""Event log: in-memory feed for the board + append-only output/audit_trail.json."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any

from config import OUTPUT, TOOL_RESULT_CHARS
from models import AgentEvent

AUDIT_PATH = OUTPUT / "audit_trail.json"
_lock = threading.Lock()
_events: list[AgentEvent] = []
_seq = 0


def _clip(text: Any) -> str:
    s = text if isinstance(text, str) else json.dumps(text, default=str)
    return s if len(s) <= TOOL_RESULT_CHARS else s[:TOOL_RESULT_CHARS] + " …[truncated]"


def _append_audit(record: dict[str, Any]) -> None:
    """Append one record. The file is a JSON array that only ever grows — never wiped."""
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(AUDIT_PATH.read_text()) if AUDIT_PATH.exists() else []
        if not isinstance(data, list):
            data = [data]
    except json.JSONDecodeError:
        # never destroy history: keep the unreadable file aside and start a new array
        AUDIT_PATH.rename(AUDIT_PATH.with_suffix(f".corrupt.{datetime.now():%Y%m%d%H%M%S}.json"))
        data = []
    data.append(record)
    tmp = AUDIT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, default=str))
    tmp.replace(AUDIT_PATH)


def emit(run_id: str, ticket_id: int, agent: str, depth: int, step: int, type_: str,
         tool: str | None = None, args: dict[str, Any] | None = None, text: Any = None) -> AgentEvent:
    global _seq
    with _lock:
        _seq += 1
        ev = AgentEvent(seq=_seq, ts=datetime.now().astimezone().isoformat(timespec="seconds"),
                        run_id=run_id, ticket_id=ticket_id, agent=agent, depth=depth, step=step,
                        type=type_, tool=tool, args=args,
                        text=None if text is None else _clip(text))
        _events.append(ev)
        _append_audit(ev.model_dump())
        return ev


def recent(since: int = 0, ticket_id: int | None = None, limit: int = 500) -> list[AgentEvent]:
    with _lock:
        out = [e for e in _events if e.seq > since and (ticket_id is None or e.ticket_id == ticket_id)]
    return out[-limit:]


def clear_feed() -> None:
    """Clears the live board feed only (audit_trail.json keeps everything)."""
    with _lock:
        _events.clear()
