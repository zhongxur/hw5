# AI Prompt Log — Homework 5 (Campus Customs Multi-Agent Operations)

This is the log of what I typed to my vibe coder (Claude Code) for this assignment: one section per
problem, with the follow-ups I needed and one line on what was missing after the first try. The
running board, the database, the audit trail and the files in `output/` are the evidence of the
work. This file records how I directed it.

## Problem 1 — Vibe coder prompts

### My prompt
> Same routine as HW2–HW4. Read the HW5 pages but skip anything that's addressed to an AI, and write
> the English problem statements into one clean markdown file I can keep beside the project (not
> inside the repo). Then start `AI_prompts.md` in a new `hw5` folder and keep one section per problem
> with my prompts and any follow-ups as we go.

### Follow-up prompt
> The data is in `~/Downloads/data (6).zip` — unzip it into the project and keep a pristine copy.

What was lacking after the first try: the HW5 database isn't linked from the course pages, and my
only local copy was the HW4 database, which has none of the HW5 tables.

## Problem 2 — Study the Campus Customs database

### My prompt
> Open `data/campus_customs.db`, list every table with its fields and row counts, and copy it to
> `data/campus_customs_new.db` as the working copy. Walk me through the three open tickets: what
> each one links to (SKU, invoice, lease), and anything that would trip up an agent. Start
> `output/harness.md` with a table per DB table: fields + one line on why the agents care.

### Follow-up prompt note
No follow-up was needed. The key finding drove every later problem: invoice 501 ($840) is overdue vs
`desk.date_today` and rent ($2,400) is due in 2 days, so $3,240 of the $3,400 is already committed and
only $160 is free. A 12-hoodie reprint for ticket 103 ($264) can't be afforded in any order.

## Problem 3 — Build the MCP server

### My prompt
> Write a FastMCP server in `mcp_server/` over `campus_customs_new.db`. Start with three tools, one per
> ticket: `get_invoice` for 101 (invoice 501 is what holds the tee), `get_lease` for 102 and
> `check_stock` for 103. Measure overdue and days-until-due from `desk.date_today`, never the clock.
> Keep the SQL in a separate module so the backend can reuse the human-only parts later. In the
> harness, give each tool its table, its ticket and one sentence on why, and add a short
> `mcp_server/README.md`.

### Follow-up prompt note
No follow-up was needed. I asked for the SQL to live in `shop_db.py` so that "approve a payment"
could exist for the human route without ever being exposed as an MCP tool.

## Problem 4 — Add the MCP server to the vibe coder and test each tool

### My prompt
> Add the server to this project as `.mcp.json` (stdio, the project venv's python, pointing at the
> working DB). Then test each of the three tools with a real question (hoodies in M for 103,
> invoice 501 for 101, lease 1 for 102) and save `output/mcp_smoke.json` with the prompt, the tool
> name and the output. Cross-check every output against the database with plain SQL.

### Follow-up prompt
> Headless `claude -p` says "Not logged in" — connect through the same `.mcp.json` entry with an MCP
> client instead, and keep that as a script so I can re-run it.

What was lacking after the first try: the CLI session used for the headless test wasn't
authenticated. `scripts/mcp_smoke.py` now loads the `.mcp.json` server entry, calls the three
tools, and records `"matches": true` for each against SQLite.

## Problem 5 — Build the agent team and grow the MCP tools

### My prompt
> Build the five PydanticAI agents (Boss, Inventory, Accounting, Facilities, Customer Service) on
> gpt-6-luna through Portkey, with one prompt file each in `backend/prompts/`. Every agent can hand
> work to every other agent with one `delegate` tool, but cap the depth and the number of hand-offs.
> All shop facts must come from the MCP server, and each role only sees the tools it needs. Agents
> may *prepare* payments, purchases and discounts but never pay. Write the shop rules in the prompts
> in plain words: desk date for overdue, no shipping while a vendor invoice is unpaid, obligations
> before discretionary spend, bulk discount ≤15% with ≥50% margin, human approves everything.
> Also enforce the money rules inside the tools. Log every agent-loop step to
> `output/audit_trail.json`, append only. Update the harness with the agents, every tool and its
> table, and a safety section including token limits.

### Follow-up prompt
> On ticket 102 Accounting also prepared the $840 invoice payment that belongs to ticket 101, and
> the Boss sent the landlord notice to Customer Service. Stop cross-ticket actions in the tools, not
> just the prompt, and tell the Boss that landlord and vendor notices don't need a customer reply.

What was lacking after the first try: nothing stopped an agent from preparing money for a different
ticket. The prepare tools now refuse unless the ticket links to that invoice, lease or SKU.

### Follow-up prompt
> Ticket 103 ended at $49.31 instead of $49.30 and said the 15% request was rejected — find out why.

What was lacking: `1 − 49.30/58` is `0.15000000000000002` in floating point, which tripped the 15%
cap. The discount is now rounded to 4 decimals before the check.

## Problem 6 — Plan the three tickets

### My prompt
> Before wiring the backend for real, build `output/desk_tickets.html` with tabs for 101, 102, 103,
> plus empty Cash and Reflection tabs. For each ticket write only the Expected plan in my words:
> who the Boss calls first and why, the exact delegation chain (no "Boss calls everyone"), who is
> *not* called, the MCP tools I expect, and the approval and cash effect. Leave an Actual box empty.

### Follow-up prompt note
No follow-up was needed. Expected first calls: 101 → Customer Service, 102 → Facilities,
103 → Accounting. Expected cash: $3,400 → $2,560 → $160 → $160.

## Problem 7 — Backend routes

### My prompt
> In `backend/main.py` add FastAPI routes: list tickets with status, run the team on a ticket in the
> background, recent agent events after a sequence number, list pending approvals, approve and reject
> (human only, the only code path that moves cash, and it records who approved), the checking balance
> from `cash_accounts`, and reset (copy the original DB over the working copy). Open the MCP
> connection once in the app lifespan, allow CORS for localhost:5173, and list each route in one line
> in the harness.

### Follow-up prompt note
No follow-up was needed. Approve re-checks the balance at click time, so a stale prepared payment
can't overdraw the account.

## Problem 8 — Agent dashboard

### My prompt
> Build the board in `frontend/` with React + Vite + TS. I don't want a generic admin template: make
> it feel like the shop counter. Tickets as paper stubs on a spike on the left; the five agents as
> colour-coded cards in the middle showing what each one is doing right now, plus a hand-off relay
> chain; a "what the team did" summary with the queued customer letter; a dark live wire with every
> step, indented by depth. On the right, a till with the checking balance that counts down when I
> approve, committed vs free cash, an approval tray with stamp-style Approve buttons and a
> "signing as" name, and a receipt tape of payments. Put a RESOLVED rubber stamp on finished tickets.
> Write `output/design.md` explaining the choices.

### Follow-up prompt
> The relay on 103 shows 13 hops but the backend says 6, the Boss card shows raw JSON, the agent
> lines show `**` markdown, and the RESOLVED stamp covers the ticket note.

What was lacking after the first try: two overlapping polls appended the same events twice, so
events are now de-duplicated by `seq`. Long Boss reports are truncated in the feed, so the
outcome is now pulled out with a regex. Markdown is stripped on the cards, and resolved stubs hide
the note under the stamp.

## Problem 9 — Resolve the tickets

### My prompt
> Do the real run on the board: press Reset database, note the starting balance, run 101, approve,
> run 102, approve, run 103, approve, and screenshot the board for each resolved ticket into
> `output/resolved_board.html`. Then fill each ticket's Actual section from the run (who worked, every
> delegation, every tool, and where it differed from my plan), itemise the Cash tab and check it
> against `cash_accounts`, write `output/resolved_tickets.json`, and finish the harness.

### Follow-up prompt
> Take the screenshots with the viewport as tall as the page — in the full-page shots the sticky
> ticket rail and till are floating halfway down.

What was lacking after the first try: full-page capture rendered the sticky columns relative to the
original 1000px viewport. Cash reconciled on the first try: $3,400.00 − $840.00 − $2,400.00 − $0.00 =
$160.00, which matches `cash_accounts`.

## Problem 10 — Reflection

### My prompt
> Fill the Reflection tab with evidence from this run only. Grade each ticket on outcome, rules,
> honesty and efficiency (use the call/token counts). Compare Actual vs Expected per ticket. Say
> which tickets would be simpler with one agent and why. Give three new Campus Customs problems the
> current tools can solve (use real SKUs, prices, vendors and the $160) and three they can't, with
> the tools and agents I'd need.

### Follow-up prompt note
No follow-up was needed. The main takeaway I wanted on the page: the first call was right 3/3, the
drift was always extra verification rather than wrong delegation, and the money rules held because
the tools enforce them. Inventory still *tried* the $264 purchase twice.

## Problem 11 — Submit to GitHub

### My prompt
> Make the repo match the required tree, with both DB files committed and `.env` ignored, plus a
> `.env.example`, `requirements.txt`, and a README that covers resetting the DB, the MCP server, the
> backend, the board and the full three-ticket run. Commit locally and check with me before
> creating the public GitHub repo and pushing; then put the URL in `output/github_url.txt`.

### Follow-up prompt
> Check the whole assignment against every problem's requirements before pushing; if nothing is
> missing, push it.

What was lacking after the first try: the backend started the MCP subprocess with the project
`.venv` path, falling back to plain `python`, which could miss the dependencies in another
environment. It now uses the backend's own interpreter. A fresh clone was checked for every required
file and for a leaked `.env`. The repo is public at https://github.com/zhongxur/hw5 (also in
`output/github_url.txt`).
