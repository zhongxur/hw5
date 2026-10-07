"""Campus Customs MCP server (FastMCP, stdio).

Every agent reads shop facts through these tools over data/campus_customs_new.db.
Agents can only READ and PREPARE. Approving a payment is not an MCP tool — only the board's
human approve route (backend/main.py) can move cash.

Run:  python mcp_server/server.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shop_db as db  # noqa: E402

mcp = FastMCP(
    "campus-customs",
    instructions=(
        "Campus Customs shop data (inventory, pricing, vendors, invoices, leases, cash, tickets). "
        "All dates are relative to desk.date_today. Payments are only prepared here; a human "
        "approves them on the board."
    ),
)


# ---------------------------------------------------------------- the first three (Problem 3)

@mcp.tool
def check_stock(sku: str, size: str | None = None) -> dict[str, Any]:
    """On-hand quantity and aisle for a SKU from the inventory table, per size.
    Pass size (S/M/L/XL/OS) to get one row, or leave it empty for every size."""
    return db.check_stock(sku, size)


@mcp.tool
def get_invoice(invoice_id: int) -> dict[str, Any]:
    """One vendor invoice (invoices joined to vendors): amount, due date, status, vendor name and
    lead days, plus days overdue measured against desk.date_today."""
    return db.get_invoice(invoice_id)


@mcp.tool
def get_lease(lease_id: int) -> dict[str, Any]:
    """One shop lease from the leases table: landlord, monthly rent, next due date, days until due
    (vs desk.date_today) and whether rent was already paid this cycle."""
    return db.get_lease(lease_id)


# ---------------------------------------------------------------- added in Problem 5

@mcp.tool
def get_desk_today() -> dict[str, Any]:
    """The shop's 'today' (desk.date_today). Use this for every overdue / due-soon decision."""
    return db.desk_today()


@mcp.tool
def list_tickets(status: str | None = None) -> list[dict[str, Any]]:
    """All desk tickets (optionally filter by status: open, in_progress, awaiting_approval, resolved)."""
    return db.list_tickets(status)


@mcp.tool
def get_ticket(ticket_id: int) -> dict[str, Any]:
    """One ticket with its type, requester, sku/size/qty and links to invoices or leases."""
    return db.get_ticket(ticket_id) or {"error": f"ticket {ticket_id} does not exist"}


@mcp.tool
def get_pricing(sku: str) -> dict[str, Any]:
    """Unit cost, list price, unit margin and gross margin % for a SKU (pricing table)."""
    return db.get_pricing(sku)


@mcp.tool
def quote_bulk_price(sku: str, qty: int, discount_pct: float) -> dict[str, Any]:
    """Check a proposed bulk discount (e.g. 15 for 15%) against shop policy: bulk minimum 12 units,
    at most 15% off list, gross margin must stay >= 50%. Returns unit price, order total, margin."""
    return db.quote_bulk_price(sku, qty, discount_pct)


@mcp.tool
def list_vendors(specialty: str | None = None) -> list[dict[str, Any]]:
    """Vendors with their specialty and lead days (optionally filter by specialty text)."""
    return db.list_vendors(specialty)


@mcp.tool
def list_open_invoices() -> list[dict[str, Any]]:
    """Every unpaid vendor invoice with days overdue vs desk.date_today."""
    return db.list_open_invoices()


@mcp.tool
def get_cash_position() -> dict[str, Any]:
    """Checking balance from cash_accounts plus committed outflows (open invoices and rent due within
    7 days), cash available after commitments, and actions already waiting for a human."""
    return db.get_cash_position()


@mcp.tool
def list_payments() -> list[dict[str, Any]]:
    """Payments already made (payments table) with who approved them."""
    return db.list_payments()


@mcp.tool
def prepare_invoice_payment(ticket_id: int, invoice_id: int, requested_by: str) -> dict[str, Any]:
    """PREPARE (not pay) a vendor invoice payment for a human to approve. requested_by = your role."""
    return db.prepare_invoice_payment(ticket_id, invoice_id, requested_by)


@mcp.tool
def prepare_rent_payment(ticket_id: int, lease_id: int, requested_by: str) -> dict[str, Any]:
    """PREPARE (not pay) a rent payment for a lease for a human to approve. requested_by = your role."""
    return db.prepare_rent_payment(ticket_id, lease_id, requested_by)


@mcp.tool
def prepare_purchase_order(ticket_id: int, vendor_id: int, sku: str, size: str, qty: int,
                           requested_by: str) -> dict[str, Any]:
    """PREPARE (not pay) a restock purchase at unit_cost for a human to approve. Refused if it would
    spend cash already committed to overdue invoices or rent due within 7 days."""
    return db.prepare_purchase_order(ticket_id, vendor_id, sku, size, qty, requested_by)


@mcp.tool
def request_price_override(ticket_id: int, sku: str, qty: int, unit_price: float, reason: str,
                           requested_by: str) -> dict[str, Any]:
    """Ask a human to approve a below-list price. Refused if it breaks discount policy."""
    return db.request_price_override(ticket_id, sku, qty, unit_price, reason, requested_by)


@mcp.tool
def list_pending_actions(ticket_id: int | None = None) -> list[dict[str, Any]]:
    """Payments / purchases / price overrides prepared by agents and their human decision status."""
    return db.list_pending_actions(ticket_id)


@mcp.tool
def queue_customer_message(ticket_id: int, message: str) -> dict[str, Any]:
    """Queue a reply to the ticket's requester (a human reviews and sends it; nothing is emailed)."""
    return db.queue_customer_message(ticket_id, message)


@mcp.tool
def list_customer_messages(ticket_id: int | None = None) -> list[dict[str, Any]]:
    """Customer replies already queued, optionally for one ticket."""
    return db.list_customer_messages(ticket_id)


@mcp.tool
def record_ticket_outcome(ticket_id: int, outcome: str) -> dict[str, Any]:
    """Boss only: record the final outcome. Ticket becomes 'resolved', or 'awaiting_approval' while
    any prepared payment / override still needs a human."""
    return db.record_ticket_outcome(ticket_id, outcome)


if __name__ == "__main__":
    mcp.run(show_banner=False)
