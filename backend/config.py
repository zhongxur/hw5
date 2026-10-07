"""Model + path configuration. Every agent uses gpt-6-luna through Portkey."""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent
OUTPUT = ROOT / "output"
PROMPTS = BACKEND / "prompts"
MCP_SERVER = ROOT / "mcp_server" / "server.py"

# project folder first, then parents (the course keeps one shared .env in ~/MBA)
for env_dir in (BACKEND, ROOT, *list(ROOT.parents)[:3]):
    load_dotenv(env_dir / ".env")

# shop_db is shared with the MCP server; the backend only uses its human-only functions
sys.path.insert(0, str(ROOT / "mcp_server"))

MODEL_NAME = "gpt-6-luna"  # the only model allowed for this homework
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1").strip()

# --- token / loop guardrails -------------------------------------------------------------
MAX_DELEGATION_DEPTH = 3      # Boss -> A -> B -> C, then no more hand-offs
MAX_DELEGATIONS_PER_RUN = 8   # hand-offs per ticket run across all agents
REQUESTS_PER_TICKET = 40      # model requests per ticket run (all agents share one usage meter)
TOKENS_PER_TICKET = 300_000   # total tokens per ticket run
MAX_OUTPUT_TOKENS = 1_500     # per model response
TOOL_RESULT_CHARS = 1_200     # tool results are truncated to this in events / audit


@lru_cache(maxsize=1)
def build_model() -> OpenAIResponsesModel:
    key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Copy .env.example to .env and add your key.")
    client = AsyncOpenAI(base_url=PORTKEY_BASE_URL, api_key=key,
                         default_headers={"x-portkey-api-key": key}, timeout=150)
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
