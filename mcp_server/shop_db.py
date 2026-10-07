"""SQLite access for Campus Customs.

Every read and write against the working database lives here. Two callers use it:

- `server.py` (the FastMCP server) exposes the read / prepare functions as MCP tools for the agents.
- `backend/main.py` imports only the human-only functions (approve / reject / reset / list) for the
  board. Those functions are deliberately NOT MCP tools, so no agent can move money.

All "today" logic uses `desk.date_today`, never the computer clock.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL_DB = ROOT / "data" / "campus_customs.db"
DB_PATH = Path(os.getenv("CAMPUS_DB", ROOT / "data" / "campus_customs_new.db"))

# Shop rules that tools enforce (the prompts explain them in words too).
BULK_MIN_QTY = 12          # orders of at least this many units of one SKU may ask for a bulk price
MAX_BULK_DISCOUNT = 0.15   # never more than 15% off list
MIN_GROSS_MARGIN = 0.50    # discounted price must keep >= 50% gross margin over unit_cost
RENT_WINDOW_DAYS = 7       # rent due within this many days counts as committed cash

# Extra tables the agent workflow needs. They are created in the working copy only; the original
# database is never touched, so a reset simply recreates them empty.
_WORKFLOW_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_actions (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    kind TEXT NOT NULL,              -- invoice_payment | rent_payment | purchase_order | price_override
    ref_id INTEGER,                  -- invoice id / lease id / vendor id
    amount REAL NOT NULL,            -- cash that leaves checking if approved (0 for price_override)
    description TEXT NOT NULL,
    payload TEXT,                    -- JSON details (sku, qty, unit price, ...)
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | approved | rejected
    created_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by TEXT
);
CREATE TABLE IF NOT EXISTS customer_messages (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    recipient TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',    -- queued for a human to send; agents never email
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ticket_outcomes (
    ticket_id INTEGER PRIMARY KEY,
    outcome TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    if not DB_PATH.exists():
        reset_database()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_WORKFLOW_SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _rows(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(r) for r in cur.fetchall()]


def _one(cur: sqlite3.Cursor) -> dict[str, Any] | None:
    r = cur.fetchone()
    return dict(r) if r else None


def _today(conn: sqlite3.Connection) -> date:
    return date.fromisoformat(conn.execute("SELECT date_today FROM desk").fetchone()[0])


def _add_month(d: date) -> date:
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return d.replace(year=y, month=m)


# ----------------------------------------------------------------------------- desk / tickets

def desk_today() -> dict[str, Any]:
    with connect() as c:
        return _one(c.execute("SELECT date_today, notes FROM desk"))


def list_tickets(status: str | None = None) -> list[dict[str, Any]]:
    with connect() as c:
        q = """SELECT t.*, o.outcome FROM tickets t
               LEFT JOIN ticket_outcomes o ON o.ticket_id = t.id"""
        if status:
            return _rows(c.execute(q + " WHERE t.status = ? ORDER BY t.id", (status,)))
        return _rows(c.execute(q + " ORDER BY t.id"))


def get_ticket(ticket_id: int) -> dict[str, Any] | None:
    with connect() as c:
        t = _one(c.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)))
        if not t:
            return None
        links = []
        if t["sku"]:
            links.append(f"inventory/pricing: sku {t['sku']} size {t['size']}")
        if t["invoice_id"]:
            links.append(f"invoices: id {t['invoice_id']}")
        if t["lease_id"]:
            links.append(f"leases: id {t['lease_id']}")
        t["linked_records"] = links
        return t


def set_ticket_status(ticket_id: int, status: str) -> None:
    with connect() as c:
        c.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))


def _refresh_ticket_status(c: sqlite3.Connection, ticket_id: int) -> str:
    """resolved once an outcome is recorded and nothing is waiting for a human."""
    has_outcome = c.execute(
        "SELECT 1 FROM ticket_outcomes WHERE ticket_id = ?", (ticket_id,)).fetchone()
    pending = c.execute(
        "SELECT COUNT(*) FROM pending_actions WHERE ticket_id = ? AND status = 'pending'",
        (ticket_id,)).fetchone()[0]
    if not has_outcome:
        status = c.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()[0]
        return status
    status = "awaiting_approval" if pending else "resolved"
    c.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
    return status


def record_ticket_outcome(ticket_id: int, outcome: str) -> dict[str, Any]:
    with connect() as c:
        if not c.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone():
            return {"error": f"ticket {ticket_id} does not exist"}
        c.execute(
            "INSERT OR REPLACE INTO ticket_outcomes (ticket_id, outcome, recorded_at) VALUES (?,?,?)",
            (ticket_id, outcome, _now()))
        status = _refresh_ticket_status(c, ticket_id)
        return {"ticket_id": ticket_id, "status": status, "outcome": outcome}


# ----------------------------------------------------------------------------- inventory / pricing

def check_stock(sku: str, size: str | None = None) -> dict[str, Any]:
    with connect() as c:
        q, args = "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ?", [sku]
        if size:
            q += " AND size = ?"
            args.append(size)
        rows = _rows(c.execute(q, args))
        if not rows:
            return {"error": f"no inventory rows for sku={sku!r} size={size!r}"}
        return {"sku": sku, "rows": rows, "total_qty": sum(r["qty"] for r in rows)}


def get_pricing(sku: str) -> dict[str, Any]:
    with connect() as c:
        p = _one(c.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)))
        if not p:
            return {"error": f"no pricing row for sku {sku!r}"}
        p["unit_margin"] = round(p["list_price"] - p["unit_cost"], 2)
        p["gross_margin_pct"] = round(100 * p["unit_margin"] / p["list_price"], 1)
        return p


def quote_bulk_price(sku: str, qty: int, discount_pct: float) -> dict[str, Any]:
    """Checks a proposed bulk discount against the shop's discount rules."""
    p = get_pricing(sku)
    if "error" in p:
        return p
    d = discount_pct / 100 if discount_pct > 1 else discount_pct
    d = round(d, 4)  # 1 - 49.30/58 is 0.15000000000000002 in floating point
    unit_price = round(p["list_price"] * (1 - d), 2)
    margin = round(unit_price - p["unit_cost"], 2)
    margin_pct = margin / unit_price if unit_price else 0
    problems = []
    if qty < BULK_MIN_QTY:
        problems.append(f"qty {qty} is below the bulk minimum of {BULK_MIN_QTY}")
    if d > MAX_BULK_DISCOUNT:
        problems.append(f"{d:.0%} is above the {MAX_BULK_DISCOUNT:.0%} bulk discount cap")
    if margin_pct < MIN_GROSS_MARGIN:
        problems.append(f"gross margin {margin_pct:.1%} is below the {MIN_GROSS_MARGIN:.0%} floor")
    return {
        "sku": sku, "qty": qty, "discount_pct": round(d * 100, 2),
        "list_price": p["list_price"], "unit_cost": p["unit_cost"],
        "unit_price": unit_price, "order_total": round(unit_price * qty, 2),
        "unit_margin": margin, "gross_margin_pct": round(margin_pct * 100, 1),
        "within_policy": not problems, "policy_problems": problems,
        "needs_human_approval": True,  # any price below list needs a human
    }


def list_vendors(specialty: str | None = None) -> list[dict[str, Any]]:
    with connect() as c:
        if specialty:
            return _rows(c.execute("SELECT * FROM vendors WHERE specialty LIKE ?", (f"%{specialty}%",)))
        return _rows(c.execute("SELECT * FROM vendors ORDER BY id"))


# ----------------------------------------------------------------------------- accounting

def get_invoice(invoice_id: int) -> dict[str, Any]:
    with connect() as c:
        inv = _one(c.execute(
            """SELECT i.*, v.name AS vendor_name, v.specialty AS vendor_specialty,
                      v.lead_days AS vendor_lead_days
               FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?""",
            (invoice_id,)))
        if not inv:
            return {"error": f"invoice {invoice_id} does not exist"}
        today = _today(c)
        days = (today - date.fromisoformat(inv["due_date"])).days
        inv["desk_date_today"] = today.isoformat()
        inv["days_overdue"] = days if inv["status"] == "open" and days > 0 else 0
        inv["is_overdue"] = inv["status"] == "open" and days > 0
        return inv


def list_open_invoices() -> list[dict[str, Any]]:
    with connect() as c:
        ids = [r[0] for r in c.execute("SELECT id FROM invoices WHERE status = 'open' ORDER BY due_date")]
    return [get_invoice(i) for i in ids]


def get_lease(lease_id: int) -> dict[str, Any]:
    with connect() as c:
        lease = _one(c.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)))
        if not lease:
            return {"error": f"lease {lease_id} does not exist"}
        today = _today(c)
        lease["desk_date_today"] = today.isoformat()
        lease["days_until_due"] = (date.fromisoformat(lease["next_due"]) - today).days
        paid = c.execute(
            "SELECT COUNT(*) FROM payments WHERE kind = 'rent' AND ref_id = ? AND paid_at >= ?",
            (lease_id, today.isoformat())).fetchone()[0]
        lease["rent_paid_this_cycle"] = bool(paid)
        return lease


def get_cash_position() -> dict[str, Any]:
    """Checking balance plus what is already committed (open invoices, rent due soon)."""
    with connect() as c:
        acct = _one(c.execute("SELECT * FROM cash_accounts WHERE name = 'checking'"))
        today = _today(c)
        open_inv = _rows(c.execute("SELECT id, amount, due_date FROM invoices WHERE status = 'open'"))
        horizon = (today + timedelta(days=RENT_WINDOW_DAYS)).isoformat()
        rent = _rows(c.execute(
            "SELECT id, space_name, monthly_rent, next_due FROM leases WHERE next_due <= ?", (horizon,)))
        pending = _rows(c.execute(
            "SELECT id, ticket_id, kind, amount FROM pending_actions WHERE status = 'pending'"))
        committed = sum(i["amount"] for i in open_inv) + sum(r["monthly_rent"] for r in rent)
        return {
            "account": "checking",
            "balance": acct["balance"],
            "balance_date": acct["date"],
            "desk_date_today": today.isoformat(),
            "open_invoices": open_inv,
            "rent_due_within_7_days": rent,
            "committed_outflows": round(committed, 2),
            "available_after_commitments": round(acct["balance"] - committed, 2),
            "pending_actions_awaiting_human": pending,
        }


def list_payments() -> list[dict[str, Any]]:
    with connect() as c:
        return _rows(c.execute("SELECT * FROM payments ORDER BY id"))


def _insert_pending(c, ticket_id, kind, ref_id, amount, description, payload, requested_by):
    dup = c.execute(
        """SELECT id FROM pending_actions WHERE ticket_id = ? AND kind = ? AND ref_id IS ?
           AND status = 'pending'""", (ticket_id, kind, ref_id)).fetchone()
    if dup:
        return {"pending_action_id": dup[0], "status": "already pending",
                "note": "An identical request is already waiting for a human."}
    cur = c.execute(
        """INSERT INTO pending_actions
           (ticket_id, kind, ref_id, amount, description, payload, requested_by, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (ticket_id, kind, ref_id, amount, description, json.dumps(payload), requested_by, _now()))
    return {"pending_action_id": cur.lastrowid, "status": "pending", "kind": kind,
            "amount": amount, "description": description,
            "note": "Prepared only. Cash does not move until a human approves it on the board."}


def _ticket_link_error(ticket_id: int, field: str, value: Any) -> dict[str, Any] | None:
    """Scope guard: an action must belong to the ticket that links to that record."""
    t = get_ticket(ticket_id)
    if not t:
        return {"error": f"ticket {ticket_id} does not exist"}
    if t[field] != value:
        return {"error": f"ticket {ticket_id} is not linked to {field}={value!r} "
                         f"(it links {field}={t[field]!r}). Prepare it only on its own ticket."}
    return None


def prepare_invoice_payment(ticket_id: int, invoice_id: int, requested_by: str) -> dict[str, Any]:
    if err := _ticket_link_error(ticket_id, "invoice_id", invoice_id):
        return err
    inv = get_invoice(invoice_id)
    if "error" in inv:
        return inv
    if inv["status"] != "open":
        return {"error": f"invoice {invoice_id} is {inv['status']}, nothing to pay"}
    with connect() as c:
        bal = c.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()[0]
        if inv["amount"] > bal:
            return {"error": f"checking balance ${bal:,.2f} cannot cover invoice ${inv['amount']:,.2f}"}
        desc = (f"Pay invoice {invoice_id} to {inv['vendor_name']} — {inv['description']} "
                f"(${inv['amount']:,.2f}, due {inv['due_date']}, {inv['days_overdue']} days overdue)")
        return _insert_pending(c, ticket_id, "invoice_payment", invoice_id, inv["amount"], desc,
                               {"vendor_id": inv["vendor_id"]}, requested_by)


def prepare_rent_payment(ticket_id: int, lease_id: int, requested_by: str) -> dict[str, Any]:
    if err := _ticket_link_error(ticket_id, "lease_id", lease_id):
        return err
    lease = get_lease(lease_id)
    if "error" in lease:
        return lease
    if lease["rent_paid_this_cycle"]:
        return {"error": f"rent for lease {lease_id} is already paid this cycle"}
    with connect() as c:
        bal = c.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()[0]
        if lease["monthly_rent"] > bal:
            return {"error": f"checking balance ${bal:,.2f} cannot cover rent ${lease['monthly_rent']:,.2f}"}
        desc = (f"Pay {lease['space_name']} rent to {lease['landlord']} "
                f"(${lease['monthly_rent']:,.2f}, due {lease['next_due']})")
        return _insert_pending(c, ticket_id, "rent_payment", lease_id, lease["monthly_rent"], desc,
                               {"next_due": lease["next_due"]}, requested_by)


def prepare_purchase_order(ticket_id: int, vendor_id: int, sku: str, size: str, qty: int,
                           requested_by: str) -> dict[str, Any]:
    """A restock buy at our unit_cost. Blocked if it would eat cash already committed."""
    if err := _ticket_link_error(ticket_id, "sku", sku):
        return err
    p = get_pricing(sku)
    if "error" in p:
        return p
    with connect() as c:
        v = _one(c.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)))
        if not v:
            return {"error": f"vendor {vendor_id} does not exist"}
        today = _today(c)
    amount = round(qty * p["unit_cost"], 2)
    pos = get_cash_position()
    if amount > pos["available_after_commitments"]:
        return {"error": "purchase blocked by cash rule",
                "purchase_amount": amount,
                "available_after_commitments": pos["available_after_commitments"],
                "committed_outflows": pos["committed_outflows"],
                "note": "Overdue invoices and rent due within 7 days come first. "
                        "Ask for a customer deposit or a smaller order instead."}
    eta = (today + timedelta(days=v["lead_days"])).isoformat()
    desc = (f"Purchase {qty} x {sku} size {size} from {v['name']} at ${p['unit_cost']:.2f} "
            f"= ${amount:,.2f}, ETA {eta}")
    with connect() as c:
        return _insert_pending(c, ticket_id, "purchase_order", vendor_id, amount, desc,
                               {"sku": sku, "size": size, "qty": qty, "eta": eta}, requested_by)


def request_price_override(ticket_id: int, sku: str, qty: int, unit_price: float, reason: str,
                           requested_by: str) -> dict[str, Any]:
    if err := _ticket_link_error(ticket_id, "sku", sku):
        return err
    p = get_pricing(sku)
    if "error" in p:
        return p
    disc = 1 - unit_price / p["list_price"]
    q = quote_bulk_price(sku, qty, disc)
    if not q["within_policy"]:
        return {"error": "price is outside discount policy", "policy_problems": q["policy_problems"]}
    desc = (f"Price override: {qty} x {sku} at ${unit_price:.2f} (list ${p['list_price']:.2f}, "
            f"{q['discount_pct']:.1f}% off, margin {q['gross_margin_pct']}%) — {reason}")
    with connect() as c:
        return _insert_pending(c, ticket_id, "price_override", None, 0.0, desc,
                               {"sku": sku, "qty": qty, "unit_price": unit_price,
                                "order_total": q["order_total"]}, requested_by)


def list_pending_actions(ticket_id: int | None = None, status: str | None = None) -> list[dict[str, Any]]:
    with connect() as c:
        q, args = "SELECT * FROM pending_actions WHERE 1=1", []
        if ticket_id is not None:
            q += " AND ticket_id = ?"
            args.append(ticket_id)
        if status:
            q += " AND status = ?"
            args.append(status)
        rows = _rows(c.execute(q + " ORDER BY id", args))
        for r in rows:
            r["payload"] = json.loads(r["payload"] or "{}")
        return rows


# ----------------------------------------------------------------------------- customer service

def queue_customer_message(ticket_id: int, message: str) -> dict[str, Any]:
    with connect() as c:
        t = _one(c.execute("SELECT requester FROM tickets WHERE id = ?", (ticket_id,)))
        if not t:
            return {"error": f"ticket {ticket_id} does not exist"}
        cur = c.execute(
            "INSERT INTO customer_messages (ticket_id, recipient, message, created_at) VALUES (?,?,?,?)",
            (ticket_id, t["requester"], message, _now()))
        return {"message_id": cur.lastrowid, "recipient": t["requester"], "status": "queued",
                "note": "Queued for a human to review and send."}


def list_customer_messages(ticket_id: int | None = None) -> list[dict[str, Any]]:
    with connect() as c:
        if ticket_id is None:
            return _rows(c.execute("SELECT * FROM customer_messages ORDER BY id"))
        return _rows(c.execute("SELECT * FROM customer_messages WHERE ticket_id = ? ORDER BY id",
                               (ticket_id,)))


# ----------------------------------------------------------------------------- human-only (board)

def decide_action(action_id: int, approve: bool, approver: str) -> dict[str, Any]:
    """The ONLY place cash moves. Called by the FastAPI approve/reject route after a human click."""
    with connect() as c:
        a = _one(c.execute("SELECT * FROM pending_actions WHERE id = ?", (action_id,)))
        if not a:
            return {"error": f"pending action {action_id} does not exist"}
        if a["status"] != "pending":
            return {"error": f"action {action_id} is already {a['status']}"}
        stamp = _now()
        if not approve:
            c.execute("UPDATE pending_actions SET status='rejected', decided_at=?, decided_by=? WHERE id=?",
                      (stamp, approver, action_id))
            return {"action_id": action_id, "status": "rejected",
                    "ticket_status": _refresh_ticket_status(c, a["ticket_id"])}

        today = _today(c)
        bal = c.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()[0]
        amount = a["amount"]
        if amount > bal:
            return {"error": f"checking ${bal:,.2f} cannot cover ${amount:,.2f}; not approved"}

        payload = json.loads(a["payload"] or "{}")
        kind_map = {"invoice_payment": "invoice", "rent_payment": "rent", "purchase_order": "purchase"}
        if a["kind"] in kind_map:
            c.execute(
                "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?,?,?,?,?,?)",
                (kind_map[a["kind"]], a["ref_id"], amount, "checking", today.isoformat(), approver))
            c.execute("UPDATE cash_accounts SET balance = ROUND(balance - ?, 2), date = ? WHERE name='checking'",
                      (amount, today.isoformat()))
        if a["kind"] == "invoice_payment":
            c.execute("UPDATE invoices SET status='paid' WHERE id=?", (a["ref_id"],))
        elif a["kind"] == "rent_payment":
            nd = date.fromisoformat(payload["next_due"])
            c.execute("UPDATE leases SET next_due=? WHERE id=?", (_add_month(nd).isoformat(), a["ref_id"]))
        c.execute("UPDATE pending_actions SET status='approved', decided_at=?, decided_by=? WHERE id=?",
                  (stamp, approver, action_id))
        new_bal = c.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()[0]
        return {"action_id": action_id, "status": "approved", "kind": a["kind"], "amount": amount,
                "balance_before": bal, "balance_after": new_bal,
                "ticket_status": _refresh_ticket_status(c, a["ticket_id"])}


def reset_database() -> dict[str, Any]:
    shutil.copyfile(ORIGINAL_DB, DB_PATH)
    with connect() as c:
        bal = c.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()[0]
    return {"reset": True, "db": DB_PATH.name, "checking_balance": bal}
