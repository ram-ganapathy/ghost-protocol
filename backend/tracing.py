"""
tracing.py — Arize OpenInference sidecar.

Initialises once at FastAPI startup. If Arize is unreachable or the env vars
are missing, /ask continues unaffected — tracing is a sidecar, never a gatekeeper.

Required env vars (in backend/.env, gitignored):
  ARIZE_API_KEY   — from arize.com → Settings → API Keys
  ARIZE_SPACE_ID  — base64 space ID from the same page

Packages (must be in requirements.txt and installed):
  arize-otel
  openinference-instrumentation-google-genai
"""
from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)

# Module-level flag so callers can query whether tracing is live.
tracing_active: bool = False


def setup_arize_tracing() -> bool:
    """
    Register Arize OTLP tracing and auto-instrument Google GenAI calls.

    Returns True if tracing started successfully, False otherwise.
    All failures are caught and logged — never raised to the caller.
    """
    global tracing_active

    api_key  = os.environ.get("ARIZE_API_KEY", "").strip()
    space_id = os.environ.get("ARIZE_SPACE_ID", "").strip()

    if not api_key or not space_id:
        _log.info(
            "Arize tracing: ARIZE_API_KEY or ARIZE_SPACE_ID not set — "
            "tracing disabled, /ask unaffected"
        )
        return False

    try:
        from arize.otel import register
        from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

        tracer_provider = register(
            space_id=space_id,
            api_key=api_key,
            project_name="ghost-protocol",
        )

        # Auto-instruments every google-genai call (which ADK uses internally).
        GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)

        tracing_active = True
        _log.info("Arize tracing: active — project=ghost-protocol")
        return True

    except Exception as exc:
        _log.warning(
            "Arize tracing: init failed (%s) — tracing disabled, /ask unaffected",
            exc,
        )
        return False
