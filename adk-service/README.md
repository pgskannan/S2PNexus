# S2PNexus ADK P2P Pipeline

A standalone Google ADK (`google-adk`) service that runs a 3-step sequential
multi-agent pipeline -- requisition intake -> supplier/sourcing check ->
receipt/invoice match -- over Gemini 3.5 Flash via Vertex AI. Built for the
[All Things Agentic Hackathon](https://allthingsagentichackathon.devpost.com/),
Fortified Enterprise Fleet track. See
`../docs/AGENTIC_HACKATHON_SUBMISSION_PLAN.md` for the full submission plan
and `../docs/AGENTIC_HACKATHON_PROJECT_STORY_DRAFT.md` for the disclosure
this pre-existing-platform reuse requires.

## Why a separate service

The main S2PNexus backend (`../backend`) is pinned to `fastapi==0.111.0`
/ `uvicorn==0.30.1`. `google-adk` (every version, back to 1.5.0) requires
`fastapi>=0.115`, `starlette>=0.46`, `uvicorn>=0.34`. Rather than force that
upgrade across the whole production backend six days before the XPRIZE
deadline, this pipeline runs as its own Cloud Run service with its own
`requirements.txt`. The backend gathers grounding data (via
`app.agents.tools`, the same functions its non-ADK domain agents use) and
calls this service over HTTP with that data attached -- so this service never
touches Postgres or backend credentials directly. See `app/pipeline.py`'s
module docstring for the full rationale.

## Architecture

```
S2PNexus backend (FastAPI, fastapi==0.111)
  -> gathers requisitions/suppliers/sourcing-events/receipts via app.agents.tools
  -> POST https://<this-service>/pipelines/p2p-intake
       Authorization: Bearer <INTERNAL_TOKEN>
       { request_text, requisitions, suppliers, sourcing_events, receipts }

This service (FastAPI, fastapi>=0.115, isolated venv/container)
  -> google.adk.workflow.Workflow: START -> requisition_step -> sourcing_step -> receipt_step
       each step: LlmAgent(model=gemini-3.5-flash) + FunctionTool(s) returning
       slices of the data already provided, output_key writes to session
       state, next step's instruction reads it back via {output_key}
  -> Vertex AI (GOOGLE_CLOUD_PROJECT=s2pnexus) generates each step's response
  <- returns one { agent_name, success, message, llm_used, latency_ms } per step

Backend logs each step to the existing Agent Activity Log
  (app.crud.agent_activity.create_agent_activity_log), so the dashboard at
  /dashboard/agent-activity shows this pipeline's steps alongside the other
  12 domain agents without any dashboard changes.
```

## Local run

```bash
cd adk-service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GOOGLE_CLOUD_PROJECT (or GEMINI_API_KEY for local dev)
uvicorn app.main:app --reload --port 8081
```

Requires Application Default Credentials for Vertex AI mode:
`gcloud auth application-default login` (or set `GOOGLE_APPLICATION_CREDENTIALS`
to a service account key with `roles/aiplatform.user` on the `s2pnexus`
project). For local dev without GCP access, set `GEMINI_API_KEY` instead and
leave `GOOGLE_CLOUD_PROJECT` unset.

Smoke test once running:

```bash
curl -X POST http://localhost:8081/pipelines/p2p-intake \
  -H "Content-Type: application/json" \
  -d '{"request_text": "run the chain", "requisitions": [{"id": "r1", "title": "Widgets"}]}'
```

## Tests

```bash
cd adk-service
pytest tests/ -v
```

No live Vertex AI calls in the test suite (mocked) -- see `tests/test_pipeline.py`.

## Deploy (Cloud Run, matches `../docs/DEPLOY_CHEATSHEET.md` conventions)

```bash
cd adk-service
gcloud run deploy s2pnexus-adk-pipeline \
  --source . \
  --region=us-central1 \
  --project=s2pnexus \
  --update-env-vars GOOGLE_CLOUD_PROJECT=s2pnexus,GOOGLE_CLOUD_LOCATION=global,GEMINI_MODEL=gemini-3.5-flash,INTERNAL_TOKEN=<generate-a-secret> \
  --no-allow-unauthenticated
```

`--no-allow-unauthenticated` plus `INTERNAL_TOKEN` is defense in depth: Cloud
Run IAM should also restrict invocation to the backend's service account, and
`INTERNAL_TOKEN` (checked in `app/main.py::_check_auth`) catches anything that
gets past IAM. This is the "Agent Gateway" / zero-trust framing for the
Fortified Enterprise Fleet track: two services, two trust boundaries, not one
monolith with an LLM bolted on.

After deploying, set on the **main backend**:

```bash
gcloud run services update s2pnexus-backend \
  --region=us-central1 --project=s2pnexus \
  --update-env-vars ADK_PIPELINE_URL=https://s2pnexus-adk-pipeline-<hash>.us-central1.run.app,ADK_PIPELINE_TOKEN=<same-secret>
```

Then hit `POST /agents/pipelines/p2p-intake` on the main backend (not this
service directly) -- that's the endpoint that gathers real data, calls this
service, and logs each step to Agent Activity.
