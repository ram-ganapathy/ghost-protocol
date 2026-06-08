"""
calendar_tool.py — Daniel Cross's calendar availability tool.

STUB: Returns hardcoded free slots so the tool-calling loop is fully proven
before OAuth is configured. Replace the body of check_availability with the
real Calendar API call in T3 (see spec/copilot_tool_calling_prompts.md → PROMPT T3).
"""


def check_availability(day: str) -> dict:
    """Checks Daniel's calendar for free time slots on a given day.

    Use this when someone asks to meet, schedule time, catch up, find a window
    to talk, or grab time with Daniel. Do not call this for purely technical questions.

    Args:
        day: The day to check, e.g. 'Thursday', 'tomorrow', or '2026-06-05'.

    Returns:
        A dict with 'day' (echoed back) and 'free_slots' (a list of
        human-readable time ranges when Daniel is available).
    """
    # ── T1 STUB — replace in T3 with real Google Calendar API ─────────────
    # Real impl: load credentials.json / token.json (both gitignored),
    # build("calendar", "v3", credentials=creds), list events for `day`,
    # compute gaps within the 9 AM–6 PM working window, return those gaps.
    return {
        "day": day,
        "free_slots": ["2:00–3:00 PM", "4:30–5:00 PM"],
    }
