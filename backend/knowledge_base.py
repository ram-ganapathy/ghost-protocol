"""
knowledge_base.py — Daniel Cross's scar fragments (grounded experience).

FRAGMENTS is the authoritative list of retrievable knowledge chunks.
Each fragment has a moral (always used) and a story (circle-tier only).

retrieve_fragments(question) returns the subset relevant to a given question
via simple keyword matching. Swap for vector search when scale demands it.
"""
from __future__ import annotations

FRAGMENTS: list[dict] = [
    {
        "id": "scar_connpool",
        "domain": "reliability",
        "trigger_keywords": [
            "release", "testing", "load", "database",
            "connection", "rewrite", "prod",
        ],
        "moral": (
            "Passing tests proves nothing about behavior at real load; "
            "small discipline lapses stay invisible until exactly the load that matters."
        ),
        "story": (
            "2011. Monthly release, fully tested, signed off. Monday morning the adjusters "
            "log in to assign coverage and at about ten concurrent users the whole thing just "
            "freezes — non-responsive JSP, nobody can do anything, and we've got 250 adjusters "
            "who can't even get in. No cloud to scale out of it back then. Four hours in a room "
            "with more managers than engineers. Turns out a new entity was getting persisted with "
            "no prepared statements, and the connection never got closed after the transaction — "
            "quietly eating a connection pool of ten. Tested fine. Of course it did. Ten users is "
            "what broke it. So when you tell me it passed testing, I hear nothing."
        ),
    },
    {
        "id": "scar_cachenode",
        "domain": "caching",
        "trigger_keywords": [
            "cache", "session", "intermittent", "inconsistent",
            "different results", "multi-node", "sometimes",
        ],
        "moral": (
            "Inconsistent output for the same input is almost always "
            "hidden distributed state, not a logic bug."
        ),
        "story": (
            "Spring web app, on-prem, had a mood of its own. Same user, same search — "
            "one time it returns the right entity, next time something completely different. "
            "Drove us up the wall chasing the query logic. It was deployed across two nodes "
            "and Spring was caching per-node instead of one distributed cache. Each node was "
            "confidently wrong in its own way. So now when something gives me two answers for "
            "one input, I don't debug the logic. I go find the state I forgot was distributed."
        ),
    },
    {
        "id": "scar_exco",
        "domain": "ea-tooling",
        "trigger_keywords": [
            "demo", "vendor", "visualization", "exec", "leadership",
            "dependency map", "straightforward",
        ],
        "moral": (
            "A vendor's easy demo path is not a defensible answer; "
            "complexity that looks clean on your screen sinks you in front of the people who matter."
        ),
        "story": (
            "We had an exco committee presentation — using our EA tool, dependency map, the vendor "
            "swore it was a two-click thing. Two clicks, sure. Then you point it at the real "
            "landscape and it's a hairball, hundreds of connections, completely unreadable. I stood "
            "there in front of the committee and the questions stopped being about the architecture "
            "and started being about whether we should decommission the tool itself. The vendor's "
            "'straightforward' and 'defensible in front of leadership' are different planets. "
            "I never demo anything now I haven't run on the real data first."
        ),
    },
]


def retrieve_fragments(question: str) -> list[dict]:
    """
    Return fragments whose trigger_keywords appear in the question (case-insensitive).
    Each matching fragment is returned at most once.
    """
    question_lower = question.lower()
    matched: list[dict] = []
    for fragment in FRAGMENTS:
        for keyword in fragment["trigger_keywords"]:
            if keyword in question_lower:
                matched.append(fragment)
                break  # one keyword match per fragment is sufficient
    return matched


def add_fragment(moral: str, domain: str, trigger_keywords: list[str]) -> dict:
    """
    Append a new fragment to the live FRAGMENTS list.
    Returns the newly created fragment.
    The fragment is active immediately — subsequent retrieve_fragments calls will find it.
    """
    new_id = f"taught_{len(FRAGMENTS) + 1}"
    fragment = {
        "id": new_id,
        "domain": domain,
        "trigger_keywords": [k.lower().strip() for k in trigger_keywords if k.strip()],
        "moral": moral.strip(),
        # No story field — taught fragments are expert corrections, not scars.
    }
    FRAGMENTS.append(fragment)
    return fragment


def list_taught_fragments() -> list[dict]:
    """
    Return only fragments added at runtime via /teach.
    These use IDs in the taught_<n> format.
    """
    return [f for f in FRAGMENTS if str(f.get("id", "")).startswith("taught_")]
