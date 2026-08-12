# All Things Agentic Hackathon — S2PNexus Submission Plan

Written 2026-08-09, updated 2026-08-09 with Resources-tab details. Submissions close
**Aug 31, 2026, 5:00pm PDT**. Track: **Fortified Enterprise Fleet** ($20,000 cash +
$2,000 GCP credits).

**Priority update, 2026-08-11:** Kannan decided S2P is a large enough project that real
revenue by Aug 17 isn't realistic, and XPRIZE will be submitted with reduced scope
(technical/product evidence + honest zero-revenue disclosure, no customer-outreach push).
**This hackathon is now the priority** — build started today (Aug 11), not Aug 18 as
originally planned, since XPRIZE no longer blocks it. $150 GCP credit confirmed approved
and applied to the `s2pnexus` billing account same day.

## Build progress (2026-08-11)

1. **Gemini 3.5 Flash model bump — done.** `GEMINI_MODEL` default changed
   `gemini-3.1-flash-lite` → `gemini-3.5-flash` in `backend/app/core/config.py`,
   `.env.example`, `docker-compose.yml`. Confirmed GA on Vertex AI.
2. **ADK wrapper — built, not yet deployed/smoke-tested live.** Real architecture change
   from the original Section 3 plan below: `google-adk` (every version back to 1.5.0)
   requires `fastapi>=0.115`/`starlette>=0.46`/`uvicorn>=0.34`, all newer than this
   backend's pins (`fastapi==0.111.0`, `uvicorn==0.30.1`). Installing it in-process would
   have forced those bumps across the whole production backend six days before XPRIZE
   judging. Built as a **separate Cloud Run service instead** — see `adk-service/README.md`
   for the full architecture and rationale. Summary: `adk-service/` runs the
   requisition→sourcing→receipt `google.adk.workflow.Workflow` (3 `LlmAgent` steps,
   Gemini 3.5 Flash via Vertex AI) over grounding data the main backend fetches and
   POSTs to it (`backend/app/agents/adk_pipeline.py` is the client); the main backend
   never installs `google-adk` and this service never touches Postgres. New backend
   endpoint: `POST /agents/pipelines/p2p-intake`, logs each step to the existing Agent
   Activity Log so the dashboard shows this pipeline alongside the other 12 domain agents
   with no dashboard changes. All unit tests (backend client + adk-service, 6 total)
   pass in isolated venvs; no live Vertex AI call made yet (sandboxed dev environment has
   no route to googleapis.com) — **still need one real deploy + live smoke test** before
   this goes in the demo video.
3. **Architecture diagram — done.** `docs/AGENTIC_HACKATHON_ARCHITECTURE.md`
   (`docs/images/agentic_hackathon_architecture.svg` for direct upload to Devpost).
4. **Frontend demo trigger — done.** `/dashboard/agent` now has a "Run P2P pipeline"
   button below the existing single-agent query form, showing all 3 steps' results —
   this is what the demo video should show running, not a raw `curl` call.
5. **Live smoke test — done, 2026-08-11.** Deployed `adk-service` and the updated backend
   directly from `C:\S2PNexus` (not Cloud Shell — confirmed working either way). Hit two
   real deploy bugs along the way, both now documented in `docs/DEPLOY_CHEATSHEET.md`:
   Windows `gcloud`'s `--update-env-vars` silently merging multiple comma-separated
   `KEY=value` pairs into one value instead of splitting them (fix: one var per command),
   and `--no-allow-unauthenticated` + a custom app-level bearer token being two independent
   auth layers (fix: `add-iam-policy-binding ... --member=allUsers --role=roles/run.invoker`
   since this is an internal service-to-service call, not end-user-facing). Once both were
   fixed, the full 3-step chain ran for real through the `/dashboard/agent` UI button:
   real Gemini 3.5 Flash reasoning at every step, correct state handoff (step 2 referenced
   the exact requisition step 1 found; step 3 correctly flagged real invoice exceptions —
   `INV2026-08-006`/`INV2026-08-005` matched-with-variance, `INV2026-08-003` exception —
   from live data). This is the first real Vertex AI call the whole build has made, and it
   worked end-to-end. Still open: confirm the 3 steps show up in `/dashboard/agent-activity`,
   demo video (record this exact run), submission text (can finally be written for real —
   see Section 2a).

## 0. Free resources to grab now (no build-time cost)

- **Devpost registration:** done 2026-08-09 (Working solo, GEAR not yet signed up).
- **$150 GCP credit form:** submitted 2026-08-09 via `https://forms.gle/5PtXmw1dSbDnpYke9`
  — name, US residency, Devpost username `pgskannan`, GCP account yes (project
  `s2pnexus`), and the Fortified Enterprise Fleet blurb. Confirmation: "Your response has
  been recorded." Google's own processing note: allow up to 72 business hours; deadline
  to request was **Aug 28, 12pm PT** (well clear); redeem before Sept 3, then 90 days to
  use once redeemed. Not guaranteed — first-come, first-served — watch email for approval
  or denial.
- **GEAR badge** (Gemini Enterprise Agent Ready) — free via Google Developer Program
  profile (`developers.google.com/program/gear`), no prerequisites. Gets 35 monthly
  Google Skills learning credits + official ADK training + skill badges. Worth claiming
  regardless of build progress since it's zero-cost and directly supports the ADK work
  planned in Section 3.
- **Relevant free webinars** (Google Cloud OnAir): "Architecting Multi-Agent Teams:
  Mastering the Three Orchestration Patterns of ADK 2" — **Aug 11**, directly useful for
  the ADK wrapper decision in Section 3, before build starts Aug 18. "Build a Long-Running
  Agent: Persistent Workflows with Google ADK" — Aug 13. Both land before the Aug 18
  build window opens, so worth watching live or catching the recording.
- Official confirmation from the Resources tab: **ADK is Google's own recommended
  framework** for exactly this kind of build (multi-agent, Vertex AI/Cloud Run-centric),
  reinforcing the Section 3 choice below over Genkit/Antigravity/GenAI SDK.

## 1. Why Fortified Enterprise Fleet fits

S2PNexus already has real substance for this track, not a from-scratch build:

| Track ask | What S2PNexus already has |
|---|---|
| Agent Registry | `app/agents/agent_registry.py` + `agent_factory.py` — 12 cataloged domain agents |
| Agent Runtime (async, long-running) | Workflow engine (approval matrix, background transitions) |
| Memory Bank (persistent cross-session context) | Postgres-backed state per tenant/entity — needs explicit framing, not new infra |
| Agent Identity (zero-trust access) | Tenant isolation + RBAC (fixed IDOR bugs 2026-07-27) |
| Agent Gateway | FastAPI routers + AI gateway service (`app/ai/service.py`) |
| Model Armor (guardrails) | **Gap** — no prompt-injection/PII-leak guardrail today |
| Agent Observability | Agent Activity dashboard (`/dashboard/agent-activity`) — tool used, plan, latency, success, already judge-facing |
| Google Cloud infra | Cloud Run (backend + frontend), live |
| Gemini via Vertex AI | Live, but wrong model version (see gap below) |

## 2. Hard gaps that block eligibility

1. **Model version.** `GEMINI_MODEL` defaults to `gemini-3.1-flash-lite`
   (`app/core/config.py`). Rules require Gemini 3.5+. Gemini 3.5 Flash is GA on Vertex AI
   — this is a one-line config change plus a smoke test, not a rebuild.
2. **No Google Agent Framework in the loop.** `app/ai/providers/gemini.py` calls Vertex AI
   directly over `httpx` — no ADK, GenAI SDK, Antigravity SDK, or Genkit. This is an
   explicit hard requirement ("At least one Google Agent Framework") and currently unmet.

## 2a. Project story placeholder

Outline drafted at docs/AGENTIC_HACKATHON_PROJECT_STORY_DRAFT.md (2026-08-09) — bracketed
placeholders only, not entered into the live Devpost form. Fill in and paste once the
Aug 18-31 build happens.

## 2b. Compliance note: "New Projects Only" rule

Official rules (checked 2026-08-09): "Projects must be newly created during the
Submission Period [Aug 3, 9am PT – Aug 31, 5pm PT]... must disclose any other
pre-existing code or work incorporated into the Project. The work described and
submitted must have been built during the Submission Period."

This does not block reusing S2PNexus — it requires disclosing it as pre-existing and
framing the *submitted Project* as the new agentic work layered on top, built inside the
Submission Period. Practical effect on the submission form:
- "What date did you start this project?" → answer with **Aug 11** (the date the
  ADK/Gemini-3.5 work actually started, moved up from the original Aug 18 plan once
  XPRIZE was descoped — see the priority update at the top of this doc), not S2PNexus's
  original build date.
- "About the project" narrative must explicitly disclose that S2PNexus is a pre-existing
  production platform and describe what's newly built during the Submission Period.

## 3. ADK gap — built 2026-08-11, as a separate microservice

Scope decision (unchanged from the original plan): wrap **one real multi-step chain** in
Google ADK rather than migrating all 12 agents. Chain, chosen because it's a genuine
multi-agent handoff and doubles as the demo-video "heavy lifting" story:

**Requisition intake → Supplier/sourcing check → Receipt/invoice 3-way match**
(`ProcurementAgent` → `SupplierAgent`/`SourcingAgent` → `ReceiptAgent` in
`app/agents/domain_agents.py`), reimplemented as an ADK Workflow that calls Gemini 3.5
Flash, with each step logged to the existing Agent Activity log so observability stays
unified across the ADK and non-ADK agents.

**Architecture change from the original plan:** this was originally scoped as an
in-process addition to the main backend. Real dependency check on 2026-08-11 found
`google-adk` (every version back to 1.5.0) requires `fastapi>=0.115`/`starlette>=0.46`/
`uvicorn>=0.34` — all newer than this backend's pins. Rather than force that upgrade
across the whole production backend, `adk-service/` is a standalone Cloud Run service
with its own `requirements.txt`, called over HTTP by the main backend
(`backend/app/agents/adk_pipeline.py`), which still owns DB access and Agent Activity
logging. Full rationale and architecture diagram-in-prose: `adk-service/README.md`. This
also strengthens the submission's architecture story — Section 4 of the judging criteria
("how you decouple systems... manage state and memory, secure credentials") is now a real
answer (two services, two trust boundaries) rather than an in-process claim.

Orchestration primitive: `google.adk.workflow.Workflow` with linear
`edges=[(START, step1), (step1, step2), (step2, step3)]` — `SequentialAgent` was the
originally-assumed primitive (most ADK tutorials show it) but `google-adk==2.6.3` flags it
deprecated in favor of `Workflow`; using the current non-deprecated primitive was a free
choice once discovered, not a tradeoff.

Everything else (the other agents, the registry, the dashboard, tenant isolation) stays as
today's proven, deployed code — it's real production infrastructure, which is a stronger
"Architectural Discipline" story than a rewrite would be under a 3-week clock.

Not in scope: Model Armor equivalent, full ADK migration of all 12 agents. Revisit only if
time allows after the core submission is done.

**Still open:** deploy `adk-service` to Cloud Run (see its README's Deploy section), wire
`ADK_PIPELINE_URL`/`ADK_PIPELINE_TOKEN` on the main backend, and run one live smoke test —
no live Vertex AI call has been made yet (built or run entirely from a sandboxed dev
environment with no route to googleapis.com).

## 4. Submission checklist (per hackathon rules)

- [ ] Category selection: Fortified Enterprise Fleet
- [ ] Hosted project URL (Cloud Run — already live)
- [ ] Text description: features/functionality, technologies used, data sources, findings/learnings
- [ ] Public/private repo URL with spin-up instructions in README (share privately with testing@devpost.com and cloudhackathons@google.com if private)
- [ ] Architecture diagram (Gemini ↔ backend ↔ DB ↔ frontend, plus the registry/runtime/identity/gateway/observability framing)
- [ ] ~4-min demo video: problem, value prop, live demo, visible proof of Google Cloud (Cloud Run console / Vertex AI logs / .run URL)
- [ ] Optional bonus: public blog/video post (must state it was made for this hackathon) and/or social post with #AllThingsAgenticHackathon

## 5. Timeline (revised 2026-08-11 — this hackathon is now the priority, XPRIZE descoped)

- **Aug 11 (done):** Model bump to Gemini 3.5 Flash. `adk-service/` built (Workflow + 3
  LlmAgent steps + backend client), all unit tests passing in isolated venvs.
- **Aug 12 – Aug 14:** Deploy `adk-service` to Cloud Run, wire it to the main backend, run
  the first live smoke test against real Vertex AI (nothing in this build has hit a real
  Gemini call yet). Fix whatever the live run surfaces.
- **Aug 15 – Aug 20:** Architecture diagram, README spin-up instructions (draft already in
  `adk-service/README.md`), fill in `AGENTIC_HACKATHON_PROJECT_STORY_DRAFT.md` for real
  once the above is genuinely done — do not backfill from imagination.
- **Aug 21 – Aug 26:** Demo video (must show the ADK service running on Cloud Run, not
  reuse the XPRIZE video), dry-run submission.
- **Aug 27 – Aug 31:** Buffer for Cloud Run credential/deploy issues (see
  `feedback_cloud_run_env_var_deploy` — verify revision health after any env var change)
  and final polish before the 5pm PDT deadline. Do not submit at the deadline.
