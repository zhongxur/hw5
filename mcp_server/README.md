# Campus Customs MCP server

**What it is for:** the one door between the five Campus Customs agents (and your vibe coder) and
the shop's data. Every agent fact — stock, prices, vendors, invoices, the lease, cash, tickets — comes
from these tools, and every money move an agent wants is only *prepared* here for a human to approve.

**Database:** `data/campus_customs_new.db` (the working copy). Override with the `CAMPUS_DB`
environment variable. The original `data/campus_customs.db` is never written.

**Built with:** [FastMCP](https://gofastmcp.com), stdio transport. `server.py` declares the tools;
`shop_db.py` holds all the SQL (the FastAPI backend imports `shop_db` only for the human-only
approve / reject / reset functions, which are intentionally **not** MCP tools).

## Run it

```bash
# from the project root
.venv/bin/python mcp_server/server.py
```

Claude Code picks it up automatically from `.mcp.json` at the project root. The backend starts one
copy of it as a subprocess when `uvicorn` boots.

## Tools

The first three (Problem 3), one per open ticket:

| Tool | Reads | For |
|---|---|---|
| `check_stock(sku, size?)` | `inventory` | 103 — 20 hoodies in M wanted, 8 on hand (also 101: tee S = 0) |
| `get_invoice(invoice_id)` | `invoices` + `vendors` | 101 — invoice 501, the overdue rush reprint holding the S tee |
| `get_lease(lease_id)` | `leases` | 102 — lease 1, $2,400 rent due 2026-09-02 |

Added in Problem 5:

| Tool | Reads / writes |
|---|---|
| `get_desk_today()` | `desk` |
| `list_tickets(status?)`, `get_ticket(ticket_id)` | `tickets` |
| `get_pricing(sku)` | `pricing` |
| `quote_bulk_price(sku, qty, discount_pct)` | `pricing` (discount policy check) |
| `list_vendors(specialty?)` | `vendors` |
| `list_open_invoices()` | `invoices`, `vendors` |
| `get_cash_position()` | `cash_accounts`, `invoices`, `leases`, `pending_actions` |
| `list_payments()` | `payments` |
| `prepare_invoice_payment(ticket_id, invoice_id, requested_by)` | writes `pending_actions` |
| `prepare_rent_payment(ticket_id, lease_id, requested_by)` | writes `pending_actions` |
| `prepare_purchase_order(ticket_id, vendor_id, sku, size, qty, requested_by)` | writes `pending_actions` (refused if it eats committed cash) |
| `request_price_override(ticket_id, sku, qty, unit_price, reason, requested_by)` | writes `pending_actions` (refused outside policy) |
| `list_pending_actions(ticket_id?)` | `pending_actions` |
| `queue_customer_message(ticket_id, message)`, `list_customer_messages(ticket_id?)` | `customer_messages` |
| `record_ticket_outcome(ticket_id, outcome)` | `ticket_outcomes`, `tickets.status` |

`pending_actions`, `customer_messages` and `ticket_outcomes` are workflow tables created in the
working copy on first use; a reset recreates them empty.
