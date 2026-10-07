"""Smoke-test the three Problem 3 MCP tools through the project's .mcp.json config.

Connects with a real MCP client (fastmcp.Client) using exactly the server entry in .mcp.json,
calls each tool, cross-checks the answer against data/campus_customs_new.db with plain SQL,
and writes output/mcp_smoke.json.   Run from the project root:  .venv/bin/python scripts/mcp_smoke.py
"""
import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from fastmcp import Client

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "campus_customs_new.db"

CASES = [
    {
        "prompt": "Using the campus-customs MCP server, how many Basic Hoodies (CC-HOOD-NAVY) do we "
                  "have in size M and where are they? Ticket 103 wants 20.",
        "tool": "check_stock",
        "args": {"sku": "CC-HOOD-NAVY", "size": "M"},
        "sql": "SELECT qty, location FROM inventory WHERE sku='CC-HOOD-NAVY' AND size='M'",
        "compare": lambda out, row: out["rows"][0]["qty"] == row[0] and out["rows"][0]["location"] == row[1],
    },
    {
        "prompt": "Use the MCP tool to pull invoice 501 linked to ticket 101. Who is it from, how much, "
                  "and is it overdue as of the desk date?",
        "tool": "get_invoice",
        "args": {"invoice_id": 501},
        "sql": "SELECT amount, due_date, status FROM invoices WHERE id=501",
        "compare": lambda out, row: (out["amount"], out["due_date"], out["status"]) == tuple(row),
    },
    {
        "prompt": "Check lease 1 with the MCP server for ticket 102: rent amount, landlord and when the "
                  "next payment is due.",
        "tool": "get_lease",
        "args": {"lease_id": 1},
        "sql": "SELECT monthly_rent, landlord, next_due FROM leases WHERE id=1",
        "compare": lambda out, row: (out["monthly_rent"], out["landlord"], out["next_due"]) == tuple(row),
    },
]


async def main() -> None:
    config = json.loads((ROOT / ".mcp.json").read_text())
    server = config["mcpServers"]["campus-customs"]
    server = {**server, "cwd": str(ROOT)}
    con = sqlite3.connect(DB)
    results = []
    async with Client({"mcpServers": {"campus-customs": server}}) as client:
        tools = [t.name for t in await client.list_tools()]
        for case in CASES:
            r = await client.call_tool(case["tool"], case["args"])
            out = r.structured_content.get("result", r.structured_content) if r.structured_content else r.data
            row = con.execute(case["sql"]).fetchone()
            results.append({
                "prompt": case["prompt"],
                "tool": f"mcp__campus-customs__{case['tool']}",
                "arguments": case["args"],
                "output": out,
                "db_check": {"sql": case["sql"], "row": list(row), "matches": bool(case["compare"](out, row))},
            })
    doc = {
        "server": "campus-customs (mcp_server/server.py, FastMCP over stdio)",
        "connection": ".mcp.json at the project root",
        "database": "data/campus_customs_new.db",
        "tested_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "tools_listed_by_server": tools,
        "tests": results,
    }
    (ROOT / "output" / "mcp_smoke.json").write_text(json.dumps(doc, indent=2))
    print(json.dumps([(t["tool"], t["db_check"]["matches"]) for t in results]))


asyncio.run(main())
