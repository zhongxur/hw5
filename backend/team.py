"""The Campus Customs agent team (PydanticAI).

Five agents — Boss, Inventory, Accounting, Facilities, Customer Service. Each one:
- reads its own prompt file from backend/prompts/<role>.md
- gets a filtered view of the ONE shared MCP toolset (mcp_server/server.py) for shop facts
- gets a `delegate` tool that can hand a sub-task to any other agent (full connectivity)

Every agent-loop step (model call, tool call, tool result, hand-off, final answer) is emitted to
the board feed and appended to output/audit_trail.json by events.emit().
"""

from __future__ import annotations

import json
import sys
import uuid
from functools import lru_cache
from typing import Any

from pydantic_ai import Agent, FunctionToolset, RunContext, UsageLimits
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import TextPart, ToolCallPart, ToolReturnPart, RetryPromptPart
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from pydantic_ai.usage import RunUsage

import events
from config import (MAX_DELEGATION_DEPTH, MAX_DELEGATIONS_PER_RUN, MAX_OUTPUT_TOKENS, MCP_SERVER,
                    PROMPTS, REQUESTS_PER_TICKET, ROOT, TOKENS_PER_TICKET, build_model)
from models import ROLE_LABELS, ROLES, BossReport, Role, TeamDeps, TeamRun

# Which MCP tools each role may see. Approving / paying is not an MCP tool at all.
ROLE_TOOLS: dict[str, set[str]] = {
    "boss": {"get_desk_today", "list_tickets", "get_ticket", "list_pending_actions",
             "list_customer_messages", "record_ticket_outcome"},
    "inventory": {"get_desk_today", "get_ticket", "check_stock", "get_pricing", "list_vendors",
                  "get_invoice", "prepare_purchase_order"},
    "accounting": {"get_desk_today", "get_ticket", "get_invoice", "list_open_invoices",
                   "get_cash_position", "list_payments", "get_pricing", "quote_bulk_price",
                   "prepare_invoice_payment", "prepare_rent_payment", "request_price_override",
                   "list_pending_actions"},
    "facilities": {"get_desk_today", "get_ticket", "get_lease", "list_payments", "list_vendors"},
    "customer_service": {"get_desk_today", "get_ticket", "check_stock", "get_pricing",
                         "list_vendors", "list_pending_actions", "list_customer_messages",
                         "queue_customer_message"},
}

_mcp: MCPToolset | None = None


def mcp_toolset() -> MCPToolset:
    """One stdio MCP connection shared by all five agents (opened in the FastAPI lifespan)."""
    global _mcp
    if _mcp is None:
        from fastmcp.client.transports import StdioTransport
        transport = StdioTransport(
            command=sys.executable,  # same interpreter as the backend, so fastmcp is installed
            args=[str(MCP_SERVER)],
            env={"FASTMCP_LOG_LEVEL": "WARNING", "CAMPUS_DB": str(ROOT / "data" / "campus_customs_new.db")},
            cwd=str(ROOT),
        )
        _mcp = MCPToolset(transport, id="campus-customs", max_retries=1, tool_error_behavior="retry")
    return _mcp


def _team_roster(me: str) -> str:
    others = [f"- `{r}` ({ROLE_LABELS[r]})" for r in ROLES if r != me]
    return ("\n\n## Your colleagues (use the `delegate` tool)\n" + "\n".join(others) +
            f"\n\nYou are `{me}`. Hand-offs are limited: at most {MAX_DELEGATION_DEPTH} levels deep and "
            f"{MAX_DELEGATIONS_PER_RUN} per ticket, so delegate only when a colleague owns the data or "
            "the decision, and give them the ticket id plus the facts you already have.")


# ----------------------------------------------------------------------------- delegation tool

delegation_tools = FunctionToolset[TeamDeps]()


@delegation_tools.tool
async def delegate(ctx: RunContext[TeamDeps], to: Role, task: str) -> str:
    """Hand a focused sub-task to another agent and get their answer back.

    Args:
        to: the colleague who owns this work (boss, inventory, accounting, facilities, customer_service).
        task: what you need, including the ticket id and the facts you already know.
    """
    d = ctx.deps
    run = d.run
    if to == d.role:
        return "You cannot delegate to yourself. Do the work with your own tools."
    if d.depth + 1 > MAX_DELEGATION_DEPTH:
        return (f"Delegation refused: depth limit {MAX_DELEGATION_DEPTH} reached. "
                "Finish with what you have and report back.")
    if run.delegations >= MAX_DELEGATIONS_PER_RUN:
        return (f"Delegation refused: this ticket already used {MAX_DELEGATIONS_PER_RUN} hand-offs. "
                "Finish with what you have and report back.")
    run.delegations += 1
    run.path.append(f"{d.role}->{to}")
    events.emit(run.run_id, run.ticket_id, d.role, d.depth, 0, "delegate", tool="delegate",
                args={"to": to, "task": task}, text=f"{ROLE_LABELS[d.role]} → {ROLE_LABELS[to]}: {task}")
    child = TeamDeps(run=run, role=to, depth=d.depth + 1)
    answer = await run_role(to, task, child, usage=ctx.usage)
    events.emit(run.run_id, run.ticket_id, d.role, d.depth, 0, "delegate_result", tool="delegate",
                args={"from": to}, text=answer)
    return answer


# ----------------------------------------------------------------------------- agents

@lru_cache(maxsize=None)
def get_agent(role: str) -> Agent:
    prompt = (PROMPTS / f"{role}.md").read_text() + _team_roster(role)
    allowed = ROLE_TOOLS[role]
    shop_tools = mcp_toolset().filtered(lambda ctx, td, allowed=allowed: td.name in allowed)
    return Agent(
        build_model(),
        name=ROLE_LABELS[role],
        deps_type=TeamDeps,
        output_type=BossReport if role == "boss" else str,
        instructions=prompt,
        toolsets=[shop_tools, delegation_tools],
        model_settings=OpenAIResponsesModelSettings(max_tokens=MAX_OUTPUT_TOKENS),
        retries=2,
    )


def _limits() -> UsageLimits:
    return UsageLimits(request_limit=REQUESTS_PER_TICKET, total_tokens_limit=TOKENS_PER_TICKET)


async def run_role(role: str, task: str, deps: TeamDeps, usage: RunUsage | None = None) -> Any:
    """Runs one agent loop step by step, emitting an event for every step."""
    run = deps.run
    agent = get_agent(role)
    events.emit(run.run_id, run.ticket_id, role, deps.depth, 0, "run_start", text=task)
    step = 0
    try:
        async with agent.iter(task, deps=deps, usage=usage, usage_limits=_limits()) as agent_run:
            async for node in agent_run:
                step += 1
                if Agent.is_model_request_node(node):
                    for part in node.request.parts:
                        if isinstance(part, ToolReturnPart) and part.tool_name != "delegate":
                            events.emit(run.run_id, run.ticket_id, role, deps.depth, step, "tool_result",
                                        tool=part.tool_name, text=part.content)
                        elif isinstance(part, RetryPromptPart):
                            events.emit(run.run_id, run.ticket_id, role, deps.depth, step, "error",
                                        tool=part.tool_name, text=part.model_response())
                elif Agent.is_call_tools_node(node):
                    for part in node.model_response.parts:
                        if isinstance(part, TextPart) and part.content.strip():
                            events.emit(run.run_id, run.ticket_id, role, deps.depth, step, "message",
                                        text=part.content)
                        elif isinstance(part, ToolCallPart) and part.tool_name not in ("delegate", "final_result"):
                            events.emit(run.run_id, run.ticket_id, role, deps.depth, step, "tool_call",
                                        tool=part.tool_name, args=part.args_as_dict())
            output = agent_run.result.output
    except Exception as exc:  # usage limits, gateway errors, ...
        events.emit(run.run_id, run.ticket_id, role, deps.depth, step, "error",
                    text=f"{type(exc).__name__}: {exc}")
        if role == "boss":
            raise
        return f"{ROLE_LABELS[role]} could not finish: {type(exc).__name__}: {exc}"
    final_text = output.model_dump_json(indent=1) if hasattr(output, "model_dump_json") else str(output)
    events.emit(run.run_id, run.ticket_id, role, deps.depth, step, "final", text=final_text)
    return output


async def run_ticket(ticket_id: int) -> dict[str, Any]:
    """Boss-led run of the whole team on one ticket. Returns a summary for the board."""
    import shop_db as db

    run = TeamRun(run_id=uuid.uuid4().hex[:8], ticket_id=ticket_id)
    usage = RunUsage()
    events.emit(run.run_id, ticket_id, "boss", 0, 0, "human", text=f"Run started on ticket {ticket_id}")
    db.set_ticket_status(ticket_id, "in_progress")
    task = (f"New desk ticket {ticket_id}. Read it, decide who owns it, delegate, and resolve it "
            "under the shop rules. Prepare (never make) any payment, purchase or price override.")
    try:
        report: BossReport = await run_role("boss", task, TeamDeps(run=run, role="boss"), usage=usage)
    except Exception as exc:
        db.set_ticket_status(ticket_id, "open")
        events.emit(run.run_id, ticket_id, "boss", 0, 0, "run_end", text=f"failed: {exc}")
        return {"run_id": run.run_id, "ticket_id": ticket_id, "error": str(exc)}

    # Safety net: make sure the outcome is recorded even if the Boss forgot the tool call.
    status = db.record_ticket_outcome(ticket_id, report.outcome)["status"]
    summary = {
        "run_id": run.run_id,
        "ticket_id": ticket_id,
        "status": status,
        "report": report.model_dump(),
        "delegation_path": run.path,
        "tools_by_agent": _tools_by_agent(run.run_id),
        "usage": {"requests": usage.requests, "input_tokens": usage.input_tokens,
                  "output_tokens": usage.output_tokens, "total_tokens": usage.total_tokens},
        "pending_actions": db.list_pending_actions(ticket_id),
        "customer_messages": db.list_customer_messages(ticket_id),
    }
    events.emit(run.run_id, ticket_id, "boss", 0, 0, "run_end",
                text=json.dumps({"status": status, "usage": summary["usage"],
                                 "delegation_path": run.path}))
    return summary


def _tools_by_agent(run_id: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for e in events.recent(0, limit=100_000):
        if e.run_id == run_id and e.type == "tool_call" and e.tool:
            out.setdefault(e.agent, [])
            if e.tool not in out[e.agent]:
                out[e.agent].append(e.tool)
    return out
