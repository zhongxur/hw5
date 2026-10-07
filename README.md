# Campus Customs — Multi-Agent Front Desk (MGT 409 HW5)

Five PydanticAI agents — **Boss, Inventory, Accounting, Facilities, Customer Service** — work the
shop's desk tickets. Every shop fact comes through a **FastMCP** server over a SQLite database, a
**FastAPI** backend runs the team, and a **React + Vite + TypeScript** board lets a human watch the
agents and approve every payment. Agents only *prepare* money moves; a human click is the only thing
that changes cash.

```
React board (5173) ──HTTP──▶ FastAPI backend (8000) ──▶ PydanticAI team (gpt-6-luna via Portkey)
                                   │                              │
                                   │ human approve / reset        │ MCP (stdio)
                                   ▼                              ▼
                         data/campus_customs_new.db ◀── mcp_server/server.py (FastMCP)
```

## Layout

| Path | What |
|---|---|
| `data/campus_customs.db` | Original data (never modified) |
| `data/campus_customs_new.db` | Working copy every agent and route uses |
| `mcp_server/server.py`, `shop_db.py` | FastMCP tools + all SQL ([README](mcp_server/README.md)) |
| `.mcp.json` | Project MCP config so Claude Code can call the tools |
| `backend/main.py` | FastAPI routes |
| `backend/team.py` | The five agents, delegation, step-by-step audit |
| `backend/models.py` | Data types (`BossReport`, `TeamDeps`, `AgentEvent`, …) |
| `backend/prompts/*.md` | One prompt per agent |
| `frontend/` | React board |
| `output/` | harness, smoke test, ticket plan/actual/cash/reflection, design, run results, audit trail |
| `scripts/mcp_smoke.py` | Re-runs the MCP smoke test and rewrites `output/mcp_smoke.json` |

## Setup (once)

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env          # put your PORTKEY_API_KEY in it
cd frontend && npm install && cd ..
```

## 1. Get a clean working database

Copy the original over the working copy whenever you want a fresh start:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

(Or press **Reset database** on the board / `curl -X POST localhost:8000/api/reset` once the backend is up.)

## 2. Start the MCP server

The backend launches its own copy of the MCP server automatically, and Claude Code launches one
from `.mcp.json`. To run it by hand (for example to try it with another MCP client):

```bash
.venv/bin/python mcp_server/server.py
```

Smoke-test the tools against the database:

```bash
.venv/bin/python scripts/mcp_smoke.py
```

## 3. Start the FastAPI backend

```bash
cd backend
../.venv/bin/uvicorn main:app --reload --port 8000
```

Routes are listed in `output/harness.md` §5 (e.g. `GET /api/tickets`, `POST /api/tickets/101/run`,
`GET /api/events`, `POST /api/approvals/{id}/approve`, `GET /api/cash`, `POST /api/reset`).

## 4. Start the React board

```bash
cd frontend
npm run dev
```

Open http://localhost:5173.

## 5. Full three-ticket run

1. **Reset the database first** (board button or `POST /api/reset`) — checking starts at $3,400.00.
2. Pick ticket **101** → *Send to the team* → watch the agent floor and live wire → **Approve** the
   prepared payment in the tray.
3. Repeat for **102** and **103**.
4. Expected ending checking balance: **$160.00** ($3,400 − $840 invoice 501 − $2,400 rent; the
   103 discount is a $0 price override). See the Cash tab in `output/desk_tickets.html`.

Every agent step and human click is appended to `output/audit_trail.json`.
