"""Data types shared by the agents and the API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
ROLES: tuple[Role, ...] = ("boss", "inventory", "accounting", "facilities", "customer_service")
ROLE_LABELS: dict[str, str] = {
    "boss": "Boss",
    "inventory": "Inventory",
    "accounting": "Accounting",
    "facilities": "Facilities",
    "customer_service": "Customer Service",
}


# ----------------------------------------------------------------------------- agent outputs

class AgentContribution(BaseModel):
    agent: Role
    did: str = Field(description="One or two sentences: what this agent found or prepared on the ticket.")


class BossReport(BaseModel):
    """The Boss's final, structured answer for one ticket."""
    ticket_id: int
    outcome: str = Field(description="Short final outcome of the ticket in plain words.")
    contributions: list[AgentContribution] = Field(
        description="One entry per agent that actually worked on the ticket (including the Boss).")
    human_approvals_needed: list[str] = Field(
        default_factory=list,
        description="Each prepared payment / purchase / price override waiting for a human, with $.")
    customer_message_queued: bool = Field(
        description="True if Customer Service queued a reply to the requester.")


# ----------------------------------------------------------------------------- run state

@dataclass
class TeamRun:
    """State shared by every agent in one ticket run (passed as PydanticAI deps)."""
    run_id: str
    ticket_id: int
    delegations: int = 0
    path: list[str] = field(default_factory=list)


@dataclass
class TeamDeps:
    run: TeamRun
    role: Role
    depth: int = 0


# ----------------------------------------------------------------------------- API bodies

class ApproveBody(BaseModel):
    approver: str = "store manager"


class AgentEvent(BaseModel):
    seq: int
    ts: str
    run_id: str
    ticket_id: int
    agent: str
    depth: int
    step: int
    type: Literal["run_start", "thinking", "tool_call", "tool_result", "delegate", "delegate_result",
                  "message", "final", "error", "run_end", "human"]
    tool: str | None = None
    args: dict[str, Any] | None = None
    text: str | None = None
