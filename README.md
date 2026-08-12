# S2PNexus

AI-native Source-to-Pay platform where Gemini-backed agents execute enterprise
procurement — requisitions, approvals, supplier onboarding, invoice matching — with
humans in control of high-risk decisions.

Live services (Google Cloud Run, project `s2pnexus`):

- Frontend: https://s2pnexus-frontend-120737021520.us-central1.run.app
- Backend API: https://s2pnexus-backend-120737021520.us-central1.run.app
- ADK pipeline (Agent Gateway): https://s2pnexus-adk-pipeline-120737021520.us-central1.run.app

For the All Things Agentic Hackathon (Fortified Enterprise Fleet track), see
[`docs/AGENTIC_HACKATHON_PROJECT_STORY_DRAFT.md`](docs/AGENTIC_HACKATHON_PROJECT_STORY_DRAFT.md)
for the submission write-up, [`docs/AGENTIC_HACKATHON_ARCHITECTURE.md`](docs/AGENTIC_HACKATHON_ARCHITECTURE.md)
for the architecture diagram, and [`adk-service/README.md`](adk-service/README.md) for
the new Google ADK multi-agent pipeline specifically.

## Architecture

- `backend/` — FastAPI 0.111 + PostgreSQL (async SQLAlchemy), Gemini via Vertex AI,
  the domain agent registry, workflow/approval engine, and Agent Activity observability.
- `frontend/` — Next.js/TypeScript app.
- `adk-service/` — standalone Cloud Run microservice running the new Google ADK
  `Workflow` pipeline (requisition intake → sourcing check → receipt/invoice match) on
  Gemini 3.5 Flash. Kept separate from `backend/` because `google-adk` requires newer
  FastAPI/Starlette/uvicorn than the production backend is pinned to — see its README
  for the full rationale.
- `tests/` — full pytest suite (unit + integration) at the repo root, not under `backend/`.

## Local spin-up

Requires Docker and Docker Compose.

```bash
cp .env.example .env
# fill in SECRET_KEY and, if using Gemini, GOOGLE_CLOUD_PROJECT / GEMINI_API_KEY
docker compose up --build
```

This starts Postgres, Redis, ChromaDB, Ollama (local fallback LLM), the backend
(`http://localhost:8000`), and the frontend (`http://localhost:3000`). By default
`AI_PROVIDER=gemini`; set `GOOGLE_APPLICATION_CREDENTIALS`/`GEMINI_API_KEY` or switch
`AI_PROVIDER=ollama` to run without live Vertex AI credentials.

To try the new ADK pipeline locally as well, see the separate spin-up steps in
[`adk-service/README.md`](adk-service/README.md#local-run) and set `ADK_PIPELINE_URL`
on the backend to point at it.

## Reproducible testing

```bash
pip install -r backend/requirements.txt
pip install pytest pytest-asyncio==0.23.8   # pin matters, see below
pytest tests/ -v
```

`pytest.ini` at the repo root sets `pythonpath = . backend`, so tests run from the repo
root, not from inside `backend/`. Some pre-existing test failures are known and tracked
as unrelated to any specific change (not regressions) — see the "known gaps" note in
project docs if a judge wants to reproduce a clean run and needs context on baseline
failures.

`adk-service/` has its own isolated test suite (`cd adk-service && pytest tests/ -v`) —
mocked, no live Vertex AI calls required to pass.

## Frontend

```bash
cd frontend
npm install
npm run dev      # http://localhost:3000
npm run lint
npm run type-check
```

## License

Built for the All Things Agentic Hackathon (Fortified Enterprise Fleet track) and the
XPRIZE submission, on top of pre-existing S2PNexus infrastructure — see the disclosure
section in `docs/AGENTIC_HACKATHON_PROJECT_STORY_DRAFT.md`.
