# Campus Customs — Agent Harness

The harness is everything around the model that makes the five agents safe and useful: the data
they can see, the MCP tools that are their only door into that data, who talks to whom, the API the
board uses, and the guardrails on money and tokens.

- Original data: `data/campus_customs.db` (never modified)
- Working copy: `data/campus_customs_new.db` (every agent and route reads/writes this one)
- Desk date: `desk.date_today = 2026-08-31` — every "overdue" / "due soon" decision uses it.

---

## 1. Tables (Problem 2)

| Table | Fields | Why it matters for the agents |
|---|---|---|
| `desk` | `date_today`, `notes` | The shop's "today". Overdue invoices and days-until-rent are measured from here, not the computer clock. |
| `tickets` | `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`, `invoice_id`, `status`, `notes`, `created_at` | The work queue. `type` tells the Boss who to call first; `sku`/`invoice_id`/`lease_id` are the foreign keys that link each ticket to the rest of the data. |
| `inventory` | `sku`, `name`, `size`, `qty`, `location` (PK `sku`+`size`) | Stock per size and aisle. Ticket 101 hits `CC-TEE-WHITE` S = 0 and ticket 103 hits `CC-HOOD-NAVY` M = 8 (20 wanted). |
| `pricing` | `sku`, `unit_cost`, `list_price` | Cost and list price, used for margin math on discounts (103) and for the cost of a restock purchase. Hoodie: $22 cost, $58 list. |
| `vendors` | `id`, `name`, `specialty`, `lead_days` | Who can restock what and how fast. Bulldog Print Co (apparel reprint, 5 days) is the vendor on invoice 501 and the only source of more hoodies/tees. |
| `leases` | `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes` | The Chapel Street lease: $2,400/month, next due 2026-09-02. Ticket 102 links to lease 1. |
| `cash_accounts` | `name`, `balance`, `date` | The one checking account ($3,400.00 at start). The board shows it; only a human-approved action changes it. |
| `payments` | `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by` | The ledger of money that actually left. Empty at start. Used to avoid double-paying and to prove who approved what. |
| `invoices` | `id`, `vendor_id`, `amount`, `due_date`, `status`, `description` | Vendor bills. Invoice 501 ($840, rush reprint of the S tee, due 2026-08-28, open) is 3 days overdue and blocks ticket 101. |

**How the three open tickets link**

- **101** (customer_order, Tauhid Zaman) → `inventory`/`pricing` via `CC-TEE-WHITE`/S (qty 0) → `invoices` 501 → `vendors` 1 (Bulldog Print Co). The tee can't ship until the overdue reprint invoice is paid.
- **102** (rent_notice, Elm City Properties) → `leases` 1 ($2,400, due 2026-09-02 = 2 days after the desk date) → `cash_accounts` / `payments`.
- **103** (price_override, Yale AI Club) → `inventory`/`pricing` via `CC-HOOD-NAVY`/M (8 on hand vs 20) → `vendors` for a reprint → `cash_accounts` for whether we can afford one.

The money puzzle hidden in the data: $840 (invoice) + $2,400 (rent) = $3,240 committed out of $3,400,
so only **$160** is free. A 12-hoodie reprint for ticket 103 would cost 12 × $22 = $264.

Workflow tables the app adds **to the working copy only** (created on first use, recreated empty on reset):
`pending_actions` (prepared payments / purchases / price overrides awaiting a human),
`customer_messages` (replies queued for a human to send), `ticket_outcomes` (Boss's final outcome).

---

## 2. MCP server

`mcp_server/server.py` — FastMCP, stdio transport, all SQL in `mcp_server/shop_db.py`.

### 2a. The first three tools (Problem 3)

| Tool | Table(s) it reads | Ticket it unlocks | Why this tool for that ticket |
|---|---|---|---|
| `get_invoice(invoice_id)` | `invoices` ⋈ `vendors` (+ `desk` for days overdue) | **101** | Ticket 101's tee is out of stock *because* invoice 501 — the rush reprint of exactly that S tee — is unpaid and 3 days overdue, so the team has to see the invoice, vendor and overdue days before promising Tauhid anything. |
| `get_lease(lease_id)` | `leases` (+ `desk`, `payments`) | **102** | The landlord's email only says "due in 2 days"; this tool returns lease 1's exact $2,400 rent, the 2026-09-02 due date and whether it is already paid, so Facilities can verify the notice before Accounting prepares any money. |
| `check_stock(sku, size)` | `inventory` | **103** (also 101) | The AI Club wants 20 hoodies in M and the shop only has 8, so the per-size count decides whether the discount is even the main problem or whether we first need a reprint; on 101 it proves S is 0. |

### 2b. Full tool list (after Problem 5)

| Tool | Table(s) | Used by | What it does |
|---|---|---|---|
| `get_desk_today` | `desk` | all | The shop's "today". |
| `list_tickets` | `tickets`, `ticket_outcomes` | Boss | All tickets + status. |
| `get_ticket` | `tickets` | all | One ticket + its links (sku / invoice / lease). |
| `check_stock` | `inventory` | Inventory, Customer Service | Qty and aisle per size. |
| `get_pricing` | `pricing` | Inventory, Accounting, Customer Service | Cost, list, unit margin, margin %. |
| `quote_bulk_price` | `pricing` | Accounting | Checks a discount against policy (≥12 units, ≤15% off, ≥50% margin). |
| `list_vendors` | `vendors` | Inventory, Facilities, Customer Service | Vendors + lead days (for ETAs). |
| `get_invoice` | `invoices`, `vendors`, `desk` | Inventory, Accounting | One invoice + days overdue. |
| `list_open_invoices` | `invoices`, `vendors` | Accounting | Every unpaid invoice. |
| `get_lease` | `leases`, `desk`, `payments` | Facilities | Lease + days until due + paid this cycle. |
| `get_cash_position` | `cash_accounts`, `invoices`, `leases`, `pending_actions` | Accounting | Balance, committed outflows, free cash, actions waiting. |
| `list_payments` | `payments` | Accounting, Facilities | Money already paid (prevents double pay). |
| `prepare_invoice_payment` | `invoices`, `cash_accounts` → writes `pending_actions` | Accounting | Prepares, never pays. Only on the ticket linked to that invoice. |
| `prepare_rent_payment` | `leases`, `cash_accounts` → writes `pending_actions` | Accounting | Prepares, never pays. Only on the ticket linked to that lease. |
| `prepare_purchase_order` | `pricing`, `vendors`, `cash_accounts`, `invoices`, `leases` → writes `pending_actions` | Inventory | Restock at unit cost; refused if it would eat committed cash. |
| `request_price_override` | `pricing` → writes `pending_actions` | Accounting | Below-list price for a human; refused if outside policy. |
| `list_pending_actions` | `pending_actions` | Boss, Accounting, Customer Service | What is waiting for a human. |
| `queue_customer_message` | `tickets` → writes `customer_messages` | Customer Service | Queues a reply (a human sends it). |
| `list_customer_messages` | `customer_messages` | Boss, Customer Service | Replies already queued. |
| `record_ticket_outcome` | writes `ticket_outcomes`, `tickets.status` | Boss | Final outcome; status becomes `resolved` or `awaiting_approval`. |

There is deliberately **no** "approve" or "pay" tool. The only code that moves cash is
`shop_db.decide_action()`, called by the board's human approve route.

---

## 3. The five agents (Problem 5)

All agents: PydanticAI `Agent`, model **gpt-6-luna** via Portkey (`backend/config.py`), prompt in
`backend/prompts/<role>.md`, a **filtered view of the one shared MCP toolset** (`backend/team.py`,
`ROLE_TOOLS`), and a `delegate(to, task)` tool that can reach **any** other agent (full connectivity).

| Agent | Owns | First-call for | MCP tools it can see |
|---|---|---|---|
| **Boss** | Dispatching and closing tickets; reviews answers against the shop rules. Returns a structured `BossReport`. | every ticket | `get_desk_today`, `list_tickets`, `get_ticket`, `list_pending_actions`, `list_customer_messages`, `record_ticket_outcome` |
| **Inventory** | Stock counts, vendors, restock ETAs, restock purchase orders. | — | `get_desk_today`, `get_ticket`, `check_stock`, `get_pricing`, `list_vendors`, `get_invoice`, `prepare_purchase_order` |
| **Accounting** | Cash, invoices, payments, every below-list price. The only role that prepares invoice / rent payments and price overrides. | `price_override` tickets | `get_desk_today`, `get_ticket`, `get_invoice`, `list_open_invoices`, `get_cash_position`, `list_payments`, `get_pricing`, `quote_bulk_price`, `prepare_invoice_payment`, `prepare_rent_payment`, `request_price_override`, `list_pending_actions` |
| **Facilities** | The lease and the landlord; verifies rent notices. | `rent_notice` tickets | `get_desk_today`, `get_ticket`, `get_lease`, `list_payments`, `list_vendors` |
| **Customer Service** | Every reply to a customer; never promises what the data doesn't show. | `customer_order` tickets | `get_desk_today`, `get_ticket`, `check_stock`, `get_pricing`, `list_vendors`, `list_pending_actions`, `list_customer_messages`, `queue_customer_message` |

**Agent loop and audit:** `team.run_role()` drives each agent with `agent.iter()` and emits one
event per step — `run_start`, `tool_call` (name + args), `tool_result` (truncated), `delegate`,
`delegate_result`, `message`, `final`, `error` — plus `human` events for approvals and resets.
Each event goes to the board feed and is **appended** to `output/audit_trail.json`
(`backend/events.py`; read-append-atomic-replace, never truncated; an unreadable file is set aside,
not overwritten). Each record has `seq`, `ts`, `run_id`, `ticket_id`, `agent`, `depth`, `step`,
`type`, `tool`, `args`, `text`.

---

## 4. Safety (Problem 5)

**Money and customers**
- **Agents prepare, humans approve.** No MCP tool can pay. `prepare_*` tools only write a
  `pending_actions` row; cash, `payments`, `invoices.status` and `leases.next_due` change only in
  `POST /api/approvals/{id}/approve`, which records the approver's name in `payments.approved_by`.
- **Scope guard.** A payment / purchase / override can only be prepared on the ticket that links to
  that invoice / lease / SKU (tool refuses otherwise), so one ticket can't spend money for another.
- **Never overdraw; obligations first.** Prepare tools refuse amounts above the balance;
  `prepare_purchase_order` refuses anything above *cash available after commitments* (open
  invoices + rent due within 7 days). The approve route re-checks the balance at click time.
- **No double pay.** Duplicate pending actions are collapsed; rent already paid this cycle is refused.
- **Discount policy in code, not just in the prompt.** ≥12 units, ≤15% off list, ≥50% gross margin;
  `request_price_override` refuses anything else, and every below-list price still needs a human.
- **Customers never get raw agent output.** Replies are queued in `customer_messages` for a human
  to send; prompts forbid sharing cost, margin, cash balance or vendor invoice amounts.
- **No invented facts.** Every number must come from a tool; dates use `desk.date_today`; ETAs are
  `date_today + vendor.lead_days` or "unknown".
- **Least privilege.** Each agent sees only the MCP tools for its role.
- **Full audit.** Every step and every human click is appended to `audit_trail.json`.
- **Reset is explicit.** `POST /api/reset` copies the original DB over the working copy; refused
  while a run is in progress.

**Token limits** (`backend/config.py`)
- One shared usage meter per ticket run (nested agents pass `ctx.usage`): **40 model requests** and
  **300k total tokens** per ticket, enforced with PydanticAI `UsageLimits`.
- **Delegation depth ≤ 3** and **≤ 8 hand-offs per ticket**; self-delegation refused.
- **1,500 max output tokens** per model response.
- Tool results are truncated to 1,200 chars in events/audit; prompts tell agents to pass known
  facts along when delegating so colleagues don't re-query.
- One model only (gpt-6-luna). Typical ticket: 15–27 requests, 27k–65k tokens.

---

## 5. API routes (Problem 7)

Base URL `http://localhost:8000` (CORS allows `http://localhost:5173`).

| Method & URL | What it does |
|---|---|
| `GET /api/tickets` | The three tickets with status (open / in_progress / awaiting_approval / resolved), running flag and pending count. |
| `GET /api/tickets/{id}` | One ticket + its pending actions, queued customer messages and the last run summary. |
| `POST /api/tickets/{id}/run` | Starts the agent team on that ticket in the background. |
| `GET /api/events?since=N&ticket_id=` | Agent events after sequence N — what each agent said, tool calls and results, hand-offs, human clicks. |
| `GET /api/approvals?status=pending` | Payments / purchases / price overrides prepared by agents. |
| `POST /api/approvals/{id}/approve` | **Human only.** Executes the prepared action: writes `payments`, lowers checking, marks invoice paid / moves rent date. |
| `POST /api/approvals/{id}/reject` | Human rejects a prepared action (no cash change). |
| `GET /api/cash` | Current checking balance from `cash_accounts`, committed outflows, free cash, payments made. |
| `POST /api/reset` | Copies `campus_customs.db` over `campus_customs_new.db` for a clean run. |
| `GET /api/agents` | The five agents and the MCP tools each can use. |
| `GET /api/health` | Model name and DB file in use. |

---

## 6. Dashboard (Problem 8)

`frontend/` — React + Vite + TypeScript, polls the routes above (0.9 s while a run is live, 2.5 s idle).

- **Ticket spike** (left): the three tickets as paper stubs with status pills and a red RESOLVED stamp.
- **Agent floor** (centre): one card per agent, coloured by role, showing state
  (idle / thinking / using a tool / waiting on colleague / done), latest line, tool and hand-off counts,
  plus a **hand-off relay** chain (Boss → Facilities → Accounting …).
- **What the team did**: the Boss's outcome, one line per agent with the MCP tools it used, the
  queued customer letter, token usage and approval decisions.
- **Live wire**: every agent-loop step, indented by delegation depth, expandable tool results.
- **Till** (right): animated checking balance, committed vs free cash, the **approval tray** with
  stamp-style Approve / Reject buttons and a "signing as" name, and a receipt tape of payments.

Details and reasoning: `output/design.md`.

---

## 7. How a ticket flows end to end

1. Board → `POST /api/tickets/{id}/run` → ticket `in_progress`.
2. Boss reads the ticket over MCP, delegates to the owner; specialists use their MCP tools and may
   delegate to each other (depth/handoff limits apply).
3. Money or price decisions become `pending_actions`; Customer Service queues replies.
4. Boss records the outcome → ticket `awaiting_approval` (if anything is pending) or `resolved`.
5. Human clicks Approve on the board → cash moves, `payments` row written, ticket `resolved`.
