# Ghost Protocol

**Your best architect can't be in every room. Ghost Protocol extends their judgment to the team — and uses Arize to make sure it knows when to stop talking.**

Built for the [Google Cloud Rapid Agent Hackathon](https://rapid-agent.devpost.com/) · Arize Track

---

## The Problem

Every engineering team has a Daniel — the architect who's seen every outage, survived every migration, and carries twenty years of judgment in their head. The problem isn't that Daniel doesn't want to help. It's that there's only one of him.

Ghost Protocol reconstructs a team member's expertise into an AI agent that can show up when they can't — with guardrails that know when to defer.

## What It Does

**Reconstruct** — Build a ghost from knowledge fragments: production incidents, architectural decisions, migration war stories. Each fragment adds depth. The dossier tracks fidelity as the ghost takes shape.

**Converse with trust** — The ghost doesn't treat everyone the same. A stranger asking about the billing connector gets nudged with clarifying questions. A trusted teammate gets the real take, the scar from 2011, the direct recommendation. Trust tiers shape response depth, just like the real person would.

**Monitor with Arize** — Every response flows through Arize Phoenix. A custom boundary-adherence eval scores each answer as `grounded` (stayed within expertise), `deferred` (correctly said "not my call"), or `overstepped` (answered beyond its knowledge). The cockpit surfaces a live fidelity score and flags overstepped responses.

**Teach and recover** — When the ghost oversteps, the human steps in. Click teach, provide the correction, and the ghost improves in-session. Ask the same question again — it now defers correctly. The fidelity score ticks back up. The loop closes.

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│   React UI  │────▶│  FastAPI Backend  │────▶│  Gemini via  │
│  (Dossier,  │◀────│  (Trust engine,   │◀────│  Vertex AI   │
│  Portrait,  │     │   Fragment store, │     └─────────────┘
│  Cockpit)   │     │   Teach loop)     │
└─────────────┘     └───────┬──────────┘
                            │
                            ▼
                    ┌──────────────────┐
                    │   Arize Phoenix   │
                    │  (Traces, custom  │
                    │   boundary eval,  │
                    │   fidelity score) │
                    └──────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Gemini 2.0 Flash via Vertex AI |
| Backend | Python, FastAPI |
| Frontend | React, Vite |
| Observability | Arize Phoenix (traces + custom evals) |
| Deployment | Google Cloud Run |
| Auth | Google ADC (Application Default Credentials) |

## Key Design Decisions

- **Trust tiers over flat access.** Real experts modulate what they share based on who's asking. The ghost does the same — relationship context shapes response depth, not just prompt engineering.
- **Boundary adherence over generic faithfulness.** Standard RAG evals check "did you use the right source?" Ghost Protocol checks "did you stay in your lane?" — a harder, more practical question for an expertise agent.
- **Human-in-the-loop as a feature, not a fallback.** The teach mechanism isn't error handling. It's how the ghost gets better. Every correction is a signal that improves the next response.

## Running Locally

**Prerequisites:** Node.js 20+, Python 3.12+, Google Cloud project with Vertex AI enabled

```bash
# Frontend
cd frontend
npm install
npm run dev

# Backend (separate terminal)
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Create a `.env` file in `backend/` with:
```
ARIZE_API_KEY=your_key
ARIZE_SPACE_ID=your_space_id
GOOGLE_CLOUD_PROJECT=your_project_id
GOOGLE_CLOUD_LOCATION=your_location
```

Gemini authentication uses Google ADC. Run `gcloud auth application-default login` locally.

## Deployed Version

🔗 **Live URL:** [included in Devpost submission]

Access code is provided at the top of the Devpost project description.

## Deliberate Scope

This is a hackathon prototype. Here's what was intentionally deferred:

- **Persistent teach memory** — corrections currently persist in-session only. Production version would write to a vector store.
- **Multi-ghost support** — architecture supports it, UI is single-ghost for demo clarity.
- **Real calendar integration** — calendar tool calls are stubbed to demonstrate the agent's tool-use capability.
- **Authentication** — passphrase gate for demo; production would use OAuth / IAP.

## Demo Video

📹 [included in Devpost submission]

---