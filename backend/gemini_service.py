import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

_PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
_LOCATION   = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

# Initialise once at import time — ADC handles auth, no API key needed.
_client = genai.Client(vertexai=True, project=_PROJECT_ID, location=_LOCATION)


def ask_gemini(system_instruction: str, user_message: str) -> str:
    """
    Send a user_message to Gemini 2.5 Flash with the given system instruction.
    Returns the model's text response, or an error string on failure.
    Authentication is via Application Default Credentials (gcloud auth login).
    """
    try:
        response = _client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
            ),
        )
        return response.text
    except Exception as exc:
        return f"[gemini error] {exc}"
