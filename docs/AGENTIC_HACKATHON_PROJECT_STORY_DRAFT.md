# All Things Agentic Hackathon — Project Story (ready to paste)

Status: **real, built and live-tested — ready for the Devpost "About the project" field.**
Devpost renders this as Markdown. Track: **Fortified Enterprise Fleet.**

---

## Inspiration

S2PNexus already had 12 Gemini-backed domain agents running in production, each grounded
in real tool calls — but every one of them answered a single question in isolation. None
of them demonstrated a real multi-agent *handoff*, where one agent's output becomes the
next agent's grounding. This hackathon, and the Fortified Enterprise Fleet track
specifically, was the reason to build that properly, on Google's own agent framework
instead of another one-off LLM call.

## Disclosure (required by contest rules)

S2PNexus is a pre-existing production Source-to-Pay platform — the requisition, sourcing,
purchase order, and invoice-matching workflow small and mid-size businesses normally can't
afford enterprise tooling for. It has been live on Google Cloud Run since late July 2026,
with 12 Gemini-backed domain agents grounded in real tool calls since its initial commit.

**What's new and built during this Submission Period (starting Aug 11, 2026), specifically
for this entry:**

- A new Google ADK multi-agent pipeline — `adk-service`, a standalone Cloud Run
  microservice — orchestrating a real 3-step handoff: requisition intake → supplier/sourcing
  check → receipt/invoice 3-way match.
- The Gemini model upgrade from `gemini-3.1-flash-lite` to `gemini-3.5-flash` (GA on
  Vertex AI), required for eligibility and now the model backing every step of the new
  pipeline.
- A new backend endpoint (`POST /agents/pipelines/p2p-intake`) and a new `/dashboard/agent`
  UI trigger ("Run P2P pipeline") so a judge can watch the chain run against real tenant
  data, not a canned script.
- Unified observability: every ADK step logs to the same Agent Activity dashboard the other
  12 production agents already use, with no dashboard changes required.
- The architecture diagram, demo video, and this write-up.

Everything else in the repository — the 12 domain agents, the workflow/approval engine, the
tenant-isolated database, the frontend — predates the Submission Period and is disclosed
here as pre-existing infrastructure the new work was built on top of.

## What it does

A judge can log into S2PNexus, open `/dashboard/agent`, and click "Run P2P pipeline." That
triggers a real Google ADK `Workflow` with three sequential `LlmAgent` steps, each backed
by Gemini 3.5 Flash on Vertex AI:

1. **Requisition intake** reads the tenant's actual open requisitions and picks the one
   that needs attention next.
2. **Sourcing check** picks up exactly where step one left off — referencing the same
   requisition — and checks real supplier and sourcing-event coverage for it.
3. **Receipt/invoice match** closes the loop against real receipt and invoice data,
   flagging genuine matching exceptions (not templated text) when they exist.

Each step's result — success, latency, message, and the tools it called — is logged to the
existing Agent Activity dashboard alongside the platform's other 12 agents, so this isn't a
side demo bolted onto the product; it's wired into the same observability surface judges
can already inspect.

This maps directly onto the Fortified Enterprise Fleet capabilities: **Agent Registry**
(`app/agents/agent_registry.py`, 12 cataloged agents plus this new pipeline), **Agent
Runtime** (async Cloud Run services, the existing workflow/approval engine), **Agent
Identity** (tenant RBAC stays entirely in the backend — the ADK service never touches the
database), **Agent Gateway** (an authenticated HTTP boundary between the backend and the
ADK service), and **Agent Observability** (the Agent Activity dashboard, unified across old
and new agents).

## How we built it

The new pipeline is Python, using Google's Agent Development Kit (`google-adk`). We used
`google.adk.workflow.Workflow` with explicit linear edges
(`edges=[(START, step1), (step1, step2), (step2, step3)]`) rather than `SequentialAgent`,
which `google-adk` now flags as deprecated in favor of `Workflow`.

The real architectural decision, and the one we'd point a judge at first: the ADK pipeline
runs as its **own Cloud Run service**, separate from the main backend, not as an in-process
addition. `google-adk` requires `fastapi>=0.115`/`starlette>=0.46`/`uvicorn>=0.34`, all
newer than the versions the production backend is pinned to. Rather than force that upgrade
across a live system carrying real tenant data, we built `adk-service/` as a standalone
Cloud Run service with its own dependency set. The main backend gathers real grounding
data — open requisitions, suppliers, sourcing events, receipts — from Postgres, then hands
it to `adk-service` over an authenticated HTTPS call. `adk-service` never touches the
database directly. That split is also our Agent Identity and Agent Gateway story: the
system holding tenant data and the system doing LLM orchestration are never the same
process.

Stack: Google ADK + Gemini 3.5 Flash via Vertex AI for the new pipeline; the existing
FastAPI/PostgreSQL backend and Next.js frontend for everything it plugs into; both new and
old pieces deployed on Cloud Run.

## Challenges we ran into

- **The dependency conflict above** was the real architectural fork in the road — it's the
  reason this shipped as two services instead of one, and it turned into a stronger
  "decoupled systems, separate trust boundaries" story than a simpler in-process build
  would have been.
- **`SequentialAgent` is deprecated** in the ADK version we used, in favor of `Workflow` —
  most tutorials still show the old primitive, so this took some digging to get right.
- **Two real Windows/Cloud Run deploy bugs**, hit and fixed live during our first end-to-end
  smoke test: `gcloud run services update --update-env-vars A=1,B=2,C=3` silently merged
  every value into the first key instead of splitting on commas on our Windows setup (fixed
  by issuing one env var per command); and `--no-allow-unauthenticated` plus a custom
  app-level bearer token turned out to be two independent auth layers, not one — Cloud
  Run's IAM check rejects a request before the app's own token check ever runs, so we
  opened IAM (`add-iam-policy-binding --member=allUsers --role=roles/run.invoker`) for this
  internal service-to-service call and kept the bearer token as the real gate.

## Accomplishments that we're proud of

Getting a real, live 3-step Gemini 3.5 Flash handoff working end-to-end across two separate
Cloud Run services — with correct state passthrough (step two genuinely referencing the
exact requisition step one found) and step three correctly flagging real invoice exceptions
pulled from live tenant data, not staged examples. Just as importantly: doing it without
touching the dashboard, the agent registry, or any of the 11 other production agents — the
new pipeline is a first-class citizen in the existing observability surface from the moment
it shipped.

## What we learned

That "add one more agent framework" is rarely a one-line dependency add in a real system —
version pinning across a production backend forces a real architecture decision, and in
this case that decision (a separate service, a real trust boundary) ended up being the
right one on its own merits, not just a workaround. We also relearned that platform-specific
CLI quirks (the Windows `gcloud` comma-splitting bug) and layered auth (Cloud Run IAM vs.
app-level tokens) can look identical to a real bug from the outside — both cost real
debugging time before we found the actual cause.

## What's next for S2PNexus

The most honest gap to flag: there's no Model Armor equivalent yet — no dedicated
prompt-injection or PII-leak guardrail on the agent-facing endpoints. That's the next
priority if this track continues past the hackathon. After that: extending the same ADK
`Workflow` pattern to more of the other 11 domain agents where a real multi-step handoff
exists (not just single-question agents), and moving the ADK service from a shared bearer
token to real Cloud Run IAM identity-token auth between the two services for a stronger
zero-trust story.

---

## Video demo

https://youtu.be/ryIev4Vj6pM — 3:32. Shows the problem/context, value proposition,
architecture (with the diagram below), the pipeline running live through all 3 steps
against real tenant data, the three deployed Cloud Run service URLs as proof of Google
Cloud, and the Agent Activity dashboard confirming the run.

## Repo

https://github.com/pgskannan/S2PNexus (public) — spin-up instructions in
`adk-service/README.md` and the top-level README.

## Hosted project URL

https://s2pnexus-frontend-120737021520.us-central1.run.app

## Architecture diagram

`docs/images/agentic_hackathon_architecture.svg` — ready for direct upload to Devpost.
