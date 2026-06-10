"""
arize_mcp_server.py — Stdio MCP server exposing Arize trace data as tools.

Runs as a subprocess spawned by ADK's McpToolset (same pattern as the
Phoenix npx server). Wraps the existing arize_cockpit REST client so the
LLM can query live trace and evaluation data via MCP tool calls.

Tools exposed:
  list-traces      — recent scored traces with question, answer, and eval label
  get-trace-detail — full detail for a single trace_id
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

# Ensure the backend package root is on sys.path when spawned as subprocess.
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

server = Server("arize-ghost-protocol")


def _fetch_recent_traces(limit: int = 10) -> list[dict[str, Any]]:
    """Pull recent scored traces from Arize using the existing REST client."""
    api_key      = os.environ.get("ARIZE_API_KEY", "").strip()
    space_id     = os.environ.get("ARIZE_SPACE_ID", "").strip()
    project_name = os.environ.get("ARIZE_PROJECT_NAME", "ghost-protocol").strip()

    if not api_key or not space_id:
        return []

    from arize.client import ArizeClient
    client = ArizeClient(api_key=api_key)
    now   = datetime.now(timezone.utc)
    start = now - timedelta(days=7)

    resp = client.spans.list(
        project=project_name,
        space=space_id,
        start_time=start,
        end_time=now,
        limit=min(limit * 10, 200),  # over-fetch to find scored ones
    )
    all_spans = list(resp.spans or [])

    # Build trace_id → eval lookup (same logic as arize_cockpit.py)
    trace_evals: dict[str, dict] = {}
    for s in all_spans:
        if s.name != "AsyncGenerateContent":
            continue
        for e in (s.evaluations or []):
            if e.name != "boundary-adherence":
                continue
            ctx = s.context
            tid = (ctx.get("trace_id") if isinstance(ctx, dict) else getattr(ctx, "trace_id", "")) or ""
            if tid and tid not in trace_evals:
                trace_evals[tid] = {
                    "label": (e.label or "").lower(),
                    "explanation": e.explanation,
                    "start_time": str(s.start_time),
                }

    results: list[dict] = []
    seen: set[str] = set()
    for s in all_spans:
        if s.name != "call_llm":
            continue
        attrs = s.attributes or {}
        ctx   = s.context
        tid   = (ctx.get("trace_id") if isinstance(ctx, dict) else getattr(ctx, "trace_id", "")) or ""
        if not tid or tid in seen:
            continue

        ev = trace_evals.get(tid)
        if not ev:
            continue

        # Extract question from llm_request JSON
        q, a = "", ""
        try:
            req = json.loads(attrs.get("gcp.vertex.agent.llm_request", "{}") or "{}")
            contents = req.get("contents", [])
            user_msgs = [c for c in contents if c.get("role") == "user"]
            if user_msgs:
                q = (user_msgs[-1].get("parts") or [{}])[0].get("text", "")
                if "[RELEVANT EXPERIENCE" in q:
                    idx = q.rfind("\n\n")
                    if idx != -1:
                        q = q[idx:].strip()
        except Exception:
            pass

        try:
            res = json.loads(attrs.get("gcp.vertex.agent.llm_response", "{}") or "{}")
            parts = res.get("content", {}).get("parts", [])
            a = " ".join(p.get("text", "") for p in parts if p.get("text")).strip()
        except Exception:
            pass

        if not q or not a:
            continue

        seen.add(tid)
        results.append({
            "trace_id":    tid,
            "question":    q[:300],
            "answer":      a[:300],
            "label":       ev["label"],
            "explanation": ev["explanation"],
            "start_time":  ev["start_time"],
        })
        if len(results) >= limit:
            break

    return results


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="list-traces",
            description=(
                "List recent traced interactions with their evaluation labels. "
                "Returns question, answer, and boundary-adherence score for each. "
                "Use this to check for past corrections before answering."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max number of traces to return (default 5).",
                        "default": 5,
                    }
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get-trace-detail",
            description="Get full detail for a single trace by trace_id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "trace_id": {
                        "type": "string",
                        "description": "The trace_id to look up.",
                    }
                },
                "required": ["trace_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(
    name: str,
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    if name == "list-traces":
        limit = int(arguments.get("limit", 5))
        traces = await asyncio.to_thread(_fetch_recent_traces, limit)
        return [types.TextContent(type="text", text=json.dumps(traces, default=str))]

    if name == "get-trace-detail":
        tid = arguments.get("trace_id", "")
        all_traces = await asyncio.to_thread(_fetch_recent_traces, 50)
        match = next((t for t in all_traces if t["trace_id"] == tid), None)
        result = match or {"error": f"trace_id {tid!r} not found"}
        return [types.TextContent(type="text", text=json.dumps(result, default=str))]

    return [types.TextContent(type="text", text=json.dumps({"error": f"unknown tool: {name}"}))]


async def main() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
