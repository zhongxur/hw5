# Design — the Campus Customs Front Desk board

The brief was "a real desk people would want to sit at". So instead of a generic admin dashboard
(sidebar, grey cards, a table), the board is built around the physical objects of a small shop
counter: a **ticket spike**, the **staff on the floor**, a **wire** you can listen in on, and the
**till** with an **approval tray** and a **receipt tape**. Everything a manager needs is on one
screen, in the order they'd look at it: what's waiting → who's working on it → what it costs me.

## Layout (three columns, one screen)

| Left — Ticket spike | Centre — The floor | Right — The till |
|---|---|---|
| The three tickets as paper stubs with a perforated tear line, ticket number in mono type, subject in a serif, status pill. | Ticket header with the one big action ("Send to the team"), then the five agent cards, the hand-off relay, the "What the team did" summary and the live wire. | Animated checking balance, committed vs free cash, the approval tray, and a receipt tape of every payment. |

- The centre column is the only one that scrolls in practice; the spike and till are **sticky**, so
  the balance and the approve buttons never leave the screen while you read a long run.
- Below 1180 px the till drops under the floor; below 780 px everything stacks, so it still works on
  a laptop half-screen or a tablet at the counter.

## How agents read differently

- **Each role has a fixed colour** used everywhere it appears — card top border, avatar, wire line,
  relay chips, summary chips: Boss navy (Yale blue), Customer Service plum, Inventory green,
  Accounting gold (money), Facilities brick (the building). After one run you recognise who is
  talking from the colour alone.
- **Agent cards show state, not just text**: *Idle* (faded), *Thinking* (lifted with a coloured
  glow), *Using a tool* (avatar pulses and the tool call is shown, e.g. `get_invoice(501)`),
  *Waiting on colleague* (amber, shows who it handed to), *Done* (green check). Cards with no part
  in a ticket stay faded, so a ticket that should not involve Facilities visibly doesn't.
- **Hand-off relay**: under the cards, the delegation path is drawn as coloured chips with arrows
  (Boss → Customer Service → Inventory → Accounting). That's the multi-agent story in one line, and
  it's what I compare against my Expected plan.
- **Live wire**: a dark panel (like a terminal or a radio log) with one line per agent-loop step,
  **indented by delegation depth** so you can see conversations nest. Tool calls are amber mono text
  with their arguments; tool results and long answers are collapsed behind "returned ▸" so the wire
  stays scannable, but every number is one click away for checking.

## How resolved tickets show up

- When the Boss finishes and a human has signed off, the ticket gets a **red rubber stamp
  "RESOLVED"** that thunks onto both the stub and the summary card (a scale-down animation with a
  slight overshoot). It's a small moment of satisfaction, the same reason people like stamping paper.
- The stub dims and its pill turns green; tickets waiting on you show an amber **"Needs your OK"**
  pill instead, so "agents are done but I'm not" is never confused with "done".
- The **What the team did** card gives the Boss's outcome in a serif headline, then one row per
  agent: role chip, what it contributed, and the MCP tools it actually called. The **queued customer
  reply** is shown as a little letter (cream paper, plum edge) so you can read exactly what the
  customer will get before anyone sends it. Token usage and each approval decision sit in the footer.

## How cash shows up

- **The till** is the visual anchor: a big tabular-number balance on Yale blue. When you approve a
  payment it **counts down like a mechanical register** (900 ms eased), so you *feel* the $2,400 rent
  leave. Under it: **Committed** (open invoices + rent due within 7 days) and **Free to spend**,
  which turns amber when it's low — on this data it's $160, which is exactly why the 103 reprint was
  refused.
- If anything is waiting, the subline shows the balance **if all pending items are approved**, so
  you know the consequence before you click.
- **Approval tray**: each prepared action is a slip with a coloured edge by kind (gold invoice, brick
  rent, green purchase, plum price override), the amount in red mono (`−$840.00`, or `$0 cash` for a
  discount), who prepared it, and a big **APPROVE** button styled as a rubber stamp. There's a
  "Signing as" field, and that name is written into `payments.approved_by` and the audit trail —
  accountability is part of the UI, not hidden in a log.
- **Receipt tape**: payments that really happened, printed in mono on a strip with a torn, scalloped
  bottom edge, each with date, kind, reference and "ok'd by".

## Small touches

- A **desk calendar** in the masthead shows `desk.date_today` (Aug 31). The agents reason about
  "overdue" from that date, so the human should see the same date, not today's real date.
- Faint ruled-paper background, Fraunces serif for headlines, Inter for UI, IBM Plex Mono for
  money and tools — warm and a bit editorial, not a SaaS template.
- The primary button presses down physically; the stamp button tilts when clicked.
- Polling speeds up to under a second while a run is live and relaxes to 2.5 s when idle; if the
  backend is down a banner tells you the exact command to start it.

## Why this matters for the job

The point of the board is trust. A manager should be able to see, in under ten seconds, *who* did
*what* with *which data*, and *what it will cost*, before they sign. Colour-coded roles, the relay
chain, collapsible evidence, and a till that only moves when they stamp it are all in service of that.
