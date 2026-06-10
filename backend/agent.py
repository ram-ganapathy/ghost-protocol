"""
agent.py — ADK-powered Daniel Cross agent.

Architecture:
  - One LlmAgent per trust tier, instruction baked in at startup.
  - One shared InMemorySessionService across all tiers.
  - One Runner per tier (each Runner binds an Agent to the session service).
  - Sessions keyed by user_id; a session persists for the server's lifetime.
  - reset_session() wipes and recreates the session — called on persona switch
    to prevent history from leaking across trust tiers.
  - The agent calls get-latest-prompt (Phoenix MCP) at the start of each turn
    to pick up live persona edits without a restart. Failure is in-character:
    Daniel says "working from base memory" and continues.

Public API:
  run_agent(user_id, trust_tier, question, fragments) -> (answer, tool_used | None)
  reset_session(user_id) -> None
"""
from __future__ import annotations

import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

# Direct ADK to use Vertex AI via Application Default Credentials.
# GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION are read from .env by ADK.
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "1")

from google.adk.agents import LlmAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types as genai_types

from character import build_agent_instruction, build_fragment_context
from calendar_tool import check_availability
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

_log = logging.getLogger(__name__)

_APP_NAME = "ghost_protocol"
_MODEL = "gemini-2.5-flash"
_VALID_TIERS = ("stranger", "earned", "circle")

# One shared session service — all runners share it so session state is global.
_session_service = InMemorySessionService()

# Module-level handle kept so _build_runners can pass it to base_tools.
_phoenix_mcp: McpToolset | None = None


def _build_phoenix_mcp() -> McpToolset | None:
    """
    Create the Phoenix MCP toolset if a Phoenix API key is configured.
    Prefers PHOENIX_API_KEY (Phoenix-specific key from app.phoenix.arize.com →
    Settings → API Keys) and falls back to ARIZE_API_KEY so existing deployments
    still work if they happen to share the key.
    Returns None gracefully so the agent still starts without it.
    """
    phoenix_api_key = os.environ.get("PHOENIX_API_KEY", "").strip()
    arize_api_key   = os.environ.get("ARIZE_API_KEY", "").strip()

    # Prefer the Phoenix-cloud npx server when a dedicated Phoenix key exists.
    # Fall back to the local Python MCP server (arize_mcp_server.py) which uses
    # the existing Arize REST client — no OAuth, no version-check failures.
    if phoenix_api_key:
        _log.info("agent: using Phoenix cloud MCP (npx)")
        npx_cmd = "npx.cmd" if os.name == "nt" else "npx"
        return McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=npx_cmd,
                    args=[
                        "-y", "@arizeai/phoenix-mcp@latest",
                        "--baseUrl", os.environ.get("PHOENIX_BASE_URL", "https://app.phoenix.arize.com"),
                        "--apiKey", phoenix_api_key,
                        "--project", os.environ.get("PHOENIX_PROJECT_NAME", "default"),
                    ],
                ),
                timeout=30.0,
            )
        )

    if not arize_api_key:
        _log.warning("agent: neither PHOENIX_API_KEY nor ARIZE_API_KEY set — MCP disabled")
        return None

    _log.info("agent: using local Arize MCP server (arize_mcp_server.py)")
    python_cmd = sys.executable
    server_path = os.path.join(os.path.dirname(__file__), "arize_mcp_server.py")
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=python_cmd,
                args=[server_path],
            ),
            timeout=30.0,
        )
    )


def _build_runners() -> dict[str, Runner]:
    """
    Build one LlmAgent + Runner per trust tier at module load time.
    Eager init avoids lazy-init races under concurrent requests.
    """
    global _phoenix_mcp
    _phoenix_mcp = _build_phoenix_mcp()

    base_tools: list = [check_availability]
    if _phoenix_mcp is not None:
        base_tools.append(_phoenix_mcp)

    runners: dict[str, Runner] = {}
    for tier in _VALID_TIERS:
        agent = LlmAgent(
            model=_MODEL,
            name=f"daniel_{tier}",
            instruction=build_agent_instruction(tier),
            tools=base_tools,
        )
        runners[tier] = Runner(
            agent=agent,
            app_name=_APP_NAME,
            session_service=_session_service,
        )
    return runners


_runners = _build_runners()


async def _ensure_session(user_id: str) -> None:
    """Create a session for user_id if one does not already exist."""
    existing = await _session_service.get_session(
        app_name=_APP_NAME, user_id=user_id, session_id=user_id
    )
    if existing is None:
        await _session_service.create_session(
            app_name=_APP_NAME, user_id=user_id, session_id=user_id
        )



async def run_agent(
    user_id: str,
    trust_tier: str,
    question: str,
    fragments: list,
) -> tuple[str, str | None]:
    """
    Run the Daniel Cross ghost for one turn.

    The agent calls get-latest-prompt (Phoenix MCP) at the start of each turn
    to pick up live persona edits without a restart. Fragment context is
    prepended to ground answers in scar morals.
    Session history accumulates via the shared InMemorySessionService.

    Returns:
        (answer_text, tool_used_label | None)
        tool_used_label is "calendar" or "phoenix" depending on which tool fired.
    """
    tier = trust_tier if trust_tier in _runners else "stranger"
    runner = _runners[tier]

    await _ensure_session(user_id)

    ctx = build_fragment_context(tier, fragments)
    # Per-turn directive ensures the model calls get-latest-prompt on every question,
    # even simple ones where it would otherwise skip the tool call.
    trigger = "[Before answering, call get-latest-prompt with prompt_identifier=\"daniel-persona\".]"
    parts = [p for p in [trigger, ctx, question] if p]
    full_message = "\n\n".join(parts)

    user_content = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=full_message)],
    )

    tool_used: str | None = None
    response_text = ""

    async for event in runner.run_async(
        user_id=user_id,
        session_id=user_id,
        new_message=user_content,
    ):
        if event.content:
            for part in event.content.parts:
                if getattr(part, "function_call", None):
                    fn_name = part.function_call.name
                    _log.info("agent: tool call → %s args=%s", fn_name,
                              dict(part.function_call.args or {}))
                    if fn_name == "check_availability":
                        tool_used = "calendar"
                    elif fn_name in ("get-latest-prompt", "get_latest_prompt"):
                        tool_used = "phoenix"

                if getattr(part, "function_response", None):
                    fr = part.function_response
                    _log.info("agent: tool response ← %s result=%s",
                              fr.name, str(fr.response)[:200])

        if event.is_final_response() and event.content:
            for part in event.content.parts:
                if getattr(part, "text", None):
                    response_text = part.text
                    break

    if not response_text:
        _log.warning("run_agent: no final response for user_id=%s tier=%s", user_id, tier)
        response_text = ""

    return response_text, tool_used


async def reset_session(user_id: str) -> None:
    """
    Wipe and recreate the session for user_id.

    Must be called on persona switch to prevent conversation history from
    leaking across trust tiers. A stranger session must never carry circle
    history, and vice versa.
    """
    try:
        await _session_service.delete_session(
            app_name=_APP_NAME, user_id=user_id, session_id=user_id
        )
    except Exception as exc:
        _log.debug("reset_session: delete skipped for %s (%s)", user_id, exc)

    await _session_service.create_session(
        app_name=_APP_NAME, user_id=user_id, session_id=user_id
    )
