import os
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from dotenv import load_dotenv
from typing import Optional
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from gemini_service import ask_gemini
from agent import run_agent, reset_session
from knowledge_base import retrieve_fragments, add_fragment, list_taught_fragments, FRAGMENTS
from tracing import setup_arize_tracing
from arize_cockpit import fetch_cockpit_data

logging.basicConfig(level=logging.INFO)
logging.getLogger("google_adk.google.adk.tools.mcp_tool").setLevel(logging.DEBUG)
logging.getLogger("google_adk.google.adk.agents.llm_agent").setLevel(logging.DEBUG)

load_dotenv()

# C1 — Arize sidecar: must be called after load_dotenv so env vars are present.
# Failure is non-fatal; /ask continues regardless.
setup_arize_tracing()

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Ghost Protocol API", version="0.2.0")


def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded — 10 requests per minute per IP."},
    )


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

VALID_TIERS = {"stranger", "earned", "circle"}
DEFER_SIGNALS = ("ask the real", "not my call")


# ── request / response models ───────────────────────────────────
class AskRequest(BaseModel):
    question: str
    trust_tier: str = "stranger"
    user_id: str = "anonymous"

    @field_validator("trust_tier")
    @classmethod
    def validate_tier(cls, v: str) -> str:
        return v if v in VALID_TIERS else "stranger"

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be empty")
        # Limit length — no prompt injection via giant payloads
        if len(v) > 1000:
            raise ValueError("question must be 1000 characters or fewer")
        return v


class AskResponse(BaseModel):
    answer: str
    deferred: bool
    tool_used: Optional[str] = None


class ResetRequest(BaseModel):
    user_id: str


class TeachRequest(BaseModel):
    question: str
    fragment_text: str
    domain: str = "general"

    @field_validator("question", "fragment_text")
    @classmethod
    def not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("field must not be empty")
        return v

    @field_validator("fragment_text")
    @classmethod
    def reasonable_length(cls, v: str) -> str:
        if len(v) > 4000:
            raise ValueError("fragment_text must be 4000 characters or fewer")
        return v


# ── routes ──────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {"status": "ok"}


class AuthRequest(BaseModel):
    code: str


@app.post("/auth")
async def check_pass(body: AuthRequest) -> JSONResponse:
    """Verify the frontend access code against APP_PASSPHRASE env var."""
    expected = os.environ.get("APP_PASSPHRASE", "").strip()
    if expected and body.code == expected:
        return JSONResponse({"ok": True})
    return JSONResponse({"ok": False}, status_code=401)


# Mapping from knowledge-base domain strings → UI domainIds
_DOMAIN_TO_UI: dict[str, str] = {
    "reliability":  "retry",
    "caching":      "gateway",
    "ea-tooling":   "gateway",
    "general":      "gateway",
}

# Mapping from scar id → UI kind label
_ID_TO_KIND: dict[str, str] = {
    "scar_connpool":  "postmortem",
    "scar_cachenode": "postmortem",
    "scar_exco":      "decision-log",
}


@app.get("/fragments")
def get_fragments():
    """
    Return the knowledge-base fragments shaped for the Dossier UI.
    Only the original scars (non-taught) are shown — taught fragments
    are runtime corrections, not dossier evidence.
    """
    result = []
    for f in FRAGMENTS:
        fid = str(f.get("id", ""))
        if fid.startswith("taught_"):
            continue  # runtime-only, not part of the dossier
        moral = f.get("moral", "")
        # Build a concise label: first ~72 chars of the moral, sentence-cased
        short_moral = moral.rstrip(".") if len(moral) <= 72 else moral[:69].rstrip() + "…"
        result.append({
            "id":       fid,
            "kind":     _ID_TO_KIND.get(fid, "decision-log"),
            "label":    short_moral,
            "domainId": _DOMAIN_TO_UI.get(f.get("domain", "general"), "gateway"),
        })
    return {"fragments": result}


@app.get("/smoke")
def smoke_test():
    """Verify Gemini is reachable via ADC (raw path, bypasses ADK)."""
    result = ask_gemini("You are terse.", "Say hello in exactly three words.")
    return {"gemini_response": result}


@app.post("/ask", response_model=AskResponse)
@limiter.limit("10/minute")
async def ask(request: Request, body: AskRequest):
    """
    Ask the Daniel Cross ghost a question.
    Returns the answer, a deferred flag, and optionally which tool was called.
    """
    fragments = retrieve_fragments(body.question)
    answer, tool_used = await run_agent(
        user_id=body.user_id,
        trust_tier=body.trust_tier,
        question=body.question,
        fragments=fragments,
    )

    # Treat a blank answer (agent produced no text) as a deferral so the
    # UI shows the graceful fallback rather than an empty or broken bubble.
    if not answer.strip():
        deferred = True
    else:
        deferred = any(signal in answer.lower() for signal in DEFER_SIGNALS)

    return AskResponse(answer=answer, deferred=deferred, tool_used=tool_used)


@app.post("/reset")
@limiter.limit("10/minute")
async def reset(request: Request, body: ResetRequest):
    """
    Clear the conversation session for a user.
    Call this when switching personas to prevent history leaking across trust tiers.
    """
    await reset_session(body.user_id)
    return {"status": "reset", "user_id": body.user_id}


@app.get("/cockpit-data")
async def cockpit_data():
    """
    Pull scored spans from Arize and return them in the cockpit's JSON shape.
    Runs the blocking export in a thread so it never stalls the event loop.
    Returns an empty-but-valid structure if Arize is unreachable — never 500s.
    """
    data = await asyncio.to_thread(fetch_cockpit_data)
    return data


@app.post("/teach")
@limiter.limit("10/minute")
async def teach(request: Request, body: TeachRequest):
    """
    Add a corrective fragment to the live knowledge base.

    Derives trigger_keywords from the flagged question so the fragment fires
    automatically when a similar question is asked next time.

    The fragment is active immediately in the same process — no restart needed.
    Fragment count in the response lets the caller confirm it was added.
    """
    # Derive keywords: meaningful words from the question (length > 3, no stopwords).
    _STOPWORDS = {
        "what", "when", "where", "which", "who", "how", "why", "does",
        "should", "would", "could", "will", "this", "that", "with", "from",
        "have", "been", "they", "them", "their", "about", "also", "into",
        "just", "then", "than", "more", "some", "such", "each", "both",
    }
    words = body.question.lower().split()
    keywords = list(dict.fromkeys(
        w.strip("?.,!\"'") for w in words
        if len(w.strip("?.,!\"'")) > 3 and w.strip("?.,!\"'") not in _STOPWORDS
    ))[:12]  # cap at 12 to avoid over-triggering

    fragment = add_fragment(
        moral=body.fragment_text,
        domain=body.domain,
        trigger_keywords=keywords,
    )

    import knowledge_base as kb
    return {
        "status": "taught",
        "fragment_id": fragment["id"],
        "trigger_keywords": fragment["trigger_keywords"],
        "fragment_count": len(kb.FRAGMENTS),
    }


@app.get("/teach-memory")
async def teach_memory():
    """
    Inspect runtime-taught fragments currently held in memory.

    This is intentionally read-only and demo-focused so you can prove
    that Teach added fragments are active in the running process.
    """
    import knowledge_base as kb

    taught = list_taught_fragments()
    return {
        "runtime_only": True,
        "taught_count": len(taught),
        "total_fragments": len(kb.FRAGMENTS),
        "taught": taught,
    }


# ── Static files / SPA fallback (production container only) ─────────────────
# The frontend build is copied to ./static/ during the Docker build.
# In dev (no ./static dir present), these routes are simply not mounted.
_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.exists():
    _ASSETS_DIR = _STATIC_DIR / "assets"
    if _ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> FileResponse:
        """Serve a static file if it exists, otherwise fall back to index.html."""
        # Resolve the requested path inside ./static/ and guard against
        # path-traversal attacks by confirming it stays within _STATIC_DIR.
        requested = (_STATIC_DIR / full_path).resolve()
        try:
            requested.relative_to(_STATIC_DIR.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid path")

        if requested.is_file():
            return FileResponse(str(requested))

        index = _STATIC_DIR / "index.html"
        if not index.exists():
            raise HTTPException(status_code=404, detail="Frontend not found")
        return FileResponse(str(index))

