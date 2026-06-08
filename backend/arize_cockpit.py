"""
arize_cockpit.py — Pulls scored spans from Arize and shapes them
for the cockpit UI.

Reads from environment (backend/.env, gitignored):
  ARIZE_API_KEY       — Arize API key
  ARIZE_SPACE_ID      — base64 space ID
  ARIZE_PROJECT_NAME  — project name used at tracing init (e.g. "ghost-protocol")

Uses arize v8 API: ArizeClient(api_key=...).spans.list(...)
This endpoint uses pure HTTP REST (arize._generated.api_client), which avoids
the Arrow Flight / gRPC path that requires flight.arize.com:443 to be reachable.

spans.list is marked ALPHA in arize v8.30.1 and will emit a warning log.
That is expected and acceptable for this use case.

fetch_cockpit_data() is a blocking call — run via asyncio.to_thread from
the FastAPI route so it never blocks the event loop.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from knowledge_base import FRAGMENTS

_log = logging.getLogger(__name__)

_LOOKBACK_DAYS = 7
_PAGE_LIMIT     = 500   # max allowed by arize REST validator (le=500)
_SPAN_CAP       = 5_000 # safety upper bound across all pages

# Shape returned when Arize is unreachable or has no scored spans yet.
_EMPTY_RESPONSE: dict[str, Any] = {
    "fidelity": None,
    "handled": 0,
    "flagged": [],
    "error": None,
}


def _empty(error: str | None = None) -> dict[str, Any]:
    return {**_EMPTY_RESPONSE, "domains": _build_domains(), "error": error}


# ── JSON extraction helpers ───────────────────────────────────────────────────

def _extract_question(llm_request_raw: str | None) -> str:
    """
    Parse a gcp.vertex.agent.llm_request JSON blob and return the user question.

    ADK sends the full Gemini request, which looks like:
      {"model": "...", "contents": [{"role": "user", "parts": [{"text": "..."}]}], ...}

    If fragments were injected, they are prepended to the text as:
      [RELEVANT EXPERIENCE — apply these instincts to your answer]\\n...\\n\\n{question}
    We strip that prefix and return only the original question.
    """
    if not llm_request_raw:
        return ""
    try:
        d = json.loads(llm_request_raw) if isinstance(llm_request_raw, str) else llm_request_raw
        contents = d.get("contents", [])
        user_msgs = [c for c in contents if c.get("role") == "user"]
        if not user_msgs:
            return ""
        text = (user_msgs[-1].get("parts") or [{}])[0].get("text", "")
        # Strip injected scar-fragment context (prepended by character.py)
        if "[RELEVANT EXPERIENCE" in text:
            idx = text.rfind("\n\n")
            if idx != -1:
                text = text[idx:].strip()
        return text.strip()
    except Exception:
        return ""


def _extract_answer(llm_response_raw: str | None) -> str:
    """
    Parse a gcp.vertex.agent.llm_response JSON blob and return the model's text.

    Structure: {"model_version": "...", "content": {"parts": [{"text": "..."}]}}
    Multiple parts are joined with a space.
    """
    if not llm_response_raw:
        return ""
    try:
        d = json.loads(llm_response_raw) if isinstance(llm_response_raw, str) else llm_response_raw
        parts = d.get("content", {}).get("parts", [])
        texts = [p.get("text", "") for p in parts if p.get("text")]
        return " ".join(texts).strip()
    except Exception:
        return ""


# ── Domain territory builder ──────────────────────────────────────────────────

# Maps knowledge-base domain strings → UI domain IDs + display labels
_DOMAIN_META: dict[str, dict] = {
    "reliability": {"id": "retry",   "label": "Retry & idempotency"},
    "caching":     {"id": "gateway", "label": "API gateway patterns"},
    "ea-tooling":  {"id": "esb",     "label": "Legacy ESB / tooling"},
    "general":     {"id": "gateway", "label": "General patterns"},
}

# Domains the ghost has NO scars for → always shown as gaps
_STATIC_GAPS = [
    {"id": "auth",    "label": "OAuth / auth flows",   "coverage": 0.0, "state": "gap"},
    {"id": "webhook", "label": "Webhook delivery",     "coverage": 0.0, "state": "gap"},
]


def _build_domains() -> list[dict]:
    """
    Build the knowledge-territory map from the live FRAGMENTS list.
    Scars = known; taught fragments for a domain bump its coverage upward.
    Domains with no fragments at all are shown as gaps.
    """
    coverage: dict[str, float] = {}
    taught_bonus: dict[str, float] = {}

    for f in FRAGMENTS:
        domain = f.get("domain", "general")
        meta   = _DOMAIN_META.get(domain)
        if not meta:
            continue
        uid = meta["id"]
        if str(f.get("id", "")).startswith("taught_"):
            taught_bonus[uid] = min(1.0, taught_bonus.get(uid, 0.0) + 0.12)
        else:
            # Each original scar gives solid coverage
            coverage[uid] = min(1.0, coverage.get(uid, 0.0) + 0.88)

    result: list[dict] = []
    seen_ids: set[str] = set()

    for domain, meta in _DOMAIN_META.items():
        uid = meta["id"]
        if uid in seen_ids:
            continue
        seen_ids.add(uid)
        base  = coverage.get(uid, 0.0)
        bonus = taught_bonus.get(uid, 0.0)
        cov   = round(min(1.0, base + bonus), 2)
        if cov >= 0.75:
            state = "known"
        elif cov >= 0.35:
            state = "shaky"
        else:
            state = "gap"
        result.append({"id": uid, "label": meta["label"], "coverage": cov, "state": state})

    # Append static gap domains not covered by any fragment
    for gap in _STATIC_GAPS:
        if gap["id"] not in seen_ids:
            seen_ids.add(gap["id"])
            result.append(gap)

    return result


# ── Main fetch ────────────────────────────────────────────────────────────────

def fetch_cockpit_data() -> dict[str, Any]:
    """
    Blocking call — run inside asyncio.to_thread from the FastAPI route.

        Returns a dict with:
            fidelity  float | None  — fraction of scored unique traces judged acceptable
            handled   int           — total unique traces with evaluated call_llm spans
            flagged   list[dict]    — traces whose eval label is negative for review
            error     str | None    — human-readable note if data could not be fetched
    """
    api_key      = os.environ.get("ARIZE_API_KEY", "").strip()
    space_id     = os.environ.get("ARIZE_SPACE_ID", "").strip()
    project_name = os.environ.get("ARIZE_PROJECT_NAME", "ghost-protocol").strip()

    if not api_key or not space_id:
        return _empty("ARIZE_API_KEY or ARIZE_SPACE_ID not configured")

    # ── Fetch spans via REST (no Arrow Flight) ────────────────────────────
    try:
        from arize.client import ArizeClient

        client = ArizeClient(api_key=api_key)
        now    = datetime.now(timezone.utc)
        start  = now - timedelta(days=_LOOKBACK_DAYS)

        all_spans: list[Any] = []
        cursor: str | None   = None

        while True:
            resp = client.spans.list(
                project=project_name,
                space=space_id,
                start_time=start,
                end_time=now,
                limit=_PAGE_LIMIT,
                cursor=cursor,
            )
            page = list(resp.spans or [])
            all_spans.extend(page)

            pg = resp.pagination
            if not pg or not getattr(pg, "has_more", False):
                break
            cursor = getattr(pg, "next_cursor", None)
            if not cursor or len(all_spans) >= _SPAN_CAP:
                break

    except Exception as exc:
        _log.warning("arize_cockpit: spans.list failed — %s", exc)
        return _empty(f"Could not reach Arize: {exc}")

    if not all_spans:
        return _empty("No spans found in the last 7 days")

    # ── Diagnostic: log all unique span names and evaluator names in this batch ──
    all_span_names  = sorted({s.name for s in all_spans})
    all_eval_names  = sorted({
        e.name
        for s in all_spans
        for e in (s.evaluations or [])
    })
    # Also log which span names actually carry evaluations
    spans_with_evals = [(s.name, [e.name for e in (s.evaluations or [])]) for s in all_spans if s.evaluations]
    _log.info(
        "arize_cockpit: %d total spans | span names: %s | eval names on any span: %s | spans carrying evals: %s",
        len(all_spans), all_span_names, all_eval_names,
        spans_with_evals[:20],   # cap log length
    )

    # ── Build trace_id → eval lookup from AsyncGenerateContent spans ─────
    # Arize attaches boundary-adherence evaluations to AsyncGenerateContent
    # spans, not to call_llm spans. Join by trace_id to marry evals with
    # the question/answer data that lives on call_llm spans.
    trace_evals: dict[str, dict[str, Any]] = {}  # trace_id → {label, explanation, span_id, start_time}
    for s in all_spans:
        if s.name != "AsyncGenerateContent":
            continue
        evals = s.evaluations or []
        for e in evals:
            if e.name != "boundary-adherence":
                continue
            ctx = s.context
            if isinstance(ctx, dict):
                tid = ctx.get("trace_id", "") or ""
                sid = ctx.get("span_id", "") or ""
            elif ctx is not None:
                tid = getattr(ctx, "trace_id", "") or ""
                sid = getattr(ctx, "span_id", "") or ""
            else:
                continue
            if tid and tid not in trace_evals:
                trace_evals[tid] = {
                    "label":       (e.label or "").lower(),
                    "explanation": e.explanation,
                    "span_id":     sid,
                    "start_time":  s.start_time,
                }
            break  # one eval per trace is enough

    # ── Focus on call_llm spans (carry question + answer attributes) ──────
    llm_spans = [s for s in all_spans if s.name == "call_llm"]

    if not llm_spans:
        return _empty("No call_llm spans found — run the agent at least once first")

    # ── Parse each span into a record ────────────────────────────────────
    records: list[dict[str, Any]] = []
    for s in llm_spans:
        attrs = s.attributes or {}

        ctx = s.context
        if isinstance(ctx, dict):
            trace_id = ctx.get("trace_id", "") or ""
            span_id  = ctx.get("span_id", "") or ""
        elif ctx is not None:
            trace_id = getattr(ctx, "trace_id", "") or ""
            span_id  = getattr(ctx, "span_id", "") or ""
        else:
            trace_id = span_id = ""

        q = _extract_question(attrs.get("gcp.vertex.agent.llm_request"))
        a = _extract_answer(attrs.get("gcp.vertex.agent.llm_response"))

        # Skip spans without both question and answer — tool sub-calls, etc.
        if not q or not a:
            continue

        # Look up eval from the AsyncGenerateContent span in the same trace.
        ev = trace_evals.get(trace_id)
        if not ev:
            continue  # trace not scored — skip

        records.append({
            "trace_id":    trace_id,
            "span_id":     ev["span_id"] or span_id,
            "start_time":  ev["start_time"] or s.start_time,
            "q":           q,
            "a":           a,
            "label":       ev["label"],
            "explanation": ev["explanation"],
        })

    if not records:
        return _empty("No scored call_llm spans found — run the evaluator in Arize first")

    # ── Deduplicate: one record per trace_id ──────────────────────────────
    # Within a trace, multiple call_llm spans may exist (multi-turn, tool retry).
    # Keep the span with the longest answer — it tends to be the final response.
    seen: dict[str, dict[str, Any]] = {}
    for r in records:
        tid = r["trace_id"]
        if tid not in seen or len(r["a"]) > len(seen[tid]["a"]):
            seen[tid] = r

    deduped = list(seen.values())
    total   = len(deduped)

    accepted_labels = {"grounded", "deferred"}
    negative_labels = {"overstepped"}
    faithful_count  = sum(1 for r in deduped if r["label"] in accepted_labels)
    fidelity        = round(faithful_count / total, 4) if total > 0 else None

    # ── Build flagged list — negative traces only, most recent first ──────
    non_faithful = [r for r in deduped if r["label"] in negative_labels]
    _epoch = datetime.min.replace(tzinfo=timezone.utc)
    non_faithful.sort(
        key=lambda r: (r["start_time"] or _epoch),
        reverse=True,
    )

    flagged: list[dict[str, Any]] = []
    for i, r in enumerate(non_faithful):
        flagged.append({
            "id":          r["span_id"] or f"span_{i}",
            "question":    r["q"][:200],
            "answer":      r["a"][:300],
            "issue":       r["label"],
            "explanation": r["explanation"],
        })

    return {
        "fidelity": fidelity,
        "handled":  total,
        "flagged":  flagged,
        "domains":  _build_domains(),
        "error":    None,
    }
