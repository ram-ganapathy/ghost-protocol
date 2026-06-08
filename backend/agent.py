"""
agent.py — ADK-powered Daniel Cross agent.

Architecture:
  - One LlmAgent per trust tier, instruction baked in at startup.
  - One shared InMemorySessionService across all tiers.
  - One Runner per tier (each Runner binds an Agent to the session service).
  - Sessions keyed by user_id; a session persists for the server's lifetime.
  - reset_session() wipes and recreates the session — called on persona switch
    to prevent history from leaking across trust tiers.

Public API:
  run_agent(user_id, trust_tier, question, fragments) -> (answer, tool_used | None)
  reset_session(user_id) -> None
"""
from __future__ import annotations

import os
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

_log = logging.getLogger(__name__)

_APP_NAME = "ghost_protocol"
_MODEL = "gemini-2.5-flash"
_VALID_TIERS = ("stranger", "earned", "circle")

# One shared session service — all runners share it so session state is global.
_session_service = InMemorySessionService()


def _build_runners() -> dict[str, Runner]:
    """
    Build one LlmAgent + Runner per trust tier at module load time.
    Eager init avoids lazy-init races under concurrent requests.
    """
    runners: dict[str, Runner] = {}
    for tier in _VALID_TIERS:
        agent = LlmAgent(
            model=_MODEL,
            name=f"daniel_{tier}",
            instruction=build_agent_instruction(tier),
            tools=[check_availability],  # ADK auto-wraps the plain function
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

    Fragment context is prepended to the user message each turn so Daniel's
    answers are grounded in the relevant scar morals (and stories for circle).
    Session history accumulates automatically via the shared InMemorySessionService.

    Returns:
        (answer_text, tool_used_label | None)
        tool_used_label is "calendar" when check_availability was called.
    """
    tier = trust_tier if trust_tier in _runners else "stranger"
    runner = _runners[tier]

    await _ensure_session(user_id)

    # Per-turn fragment context prepended to the raw question.
    ctx = build_fragment_context(tier, fragments)
    full_message = f"{ctx}\n\n{question}" if ctx else question

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
        # Detect tool invocations for the T4 "checking..." frontend beat.
        if event.content:
            for part in event.content.parts:
                if getattr(part, "function_call", None):
                    fn_name = part.function_call.name
                    if fn_name == "check_availability":
                        tool_used = "calendar"

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
