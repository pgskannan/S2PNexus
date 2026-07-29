# Written Narrative — Draft Outline (500-1000 words)

Status: **outline only, not yet drafted into prose.** Fill in when we sit down to write
the final narrative (task: "Film 3-min demo video + write 500-1000 word narrative").
Devpost requires this to cover: AI day-to-day usage, human vs. AI division of labor,
jobs/economic opportunity created, and the build story. Open with the AI architecture
story (agreed framing below), then flow into the rest.

## Opening: AI architecture — lead with rationale, not a feature list

Order, per [[feedback_s2pnexus_ai_narrative_framing]]:

1. **What the agents are and why each exists.** 12 domain agents, one per operational
   area of the platform: Procurement (requisitions/POs), Supplier (lookup, lifecycle,
   duplicate detection), Contract (status/terms/obligations), Sourcing (RFI/RFP/RFQ
   events), SpendAnalysis (spend/savings/concentration), Document (stored file lookup),
   Knowledge (object/reference lookup), Reporting (cross-domain status), Receipt
   (goods-receipt/invoice-match review), SupplierRisk (elevated risk flags),
   ContractAuthoring (template/clause drafting help), ContractRisk (overdue obligations).
   Each maps to a real job a procurement operator does today by hand.

2. **The grounding mechanism — NOT RAG.** Every agent gathers live data via a real tool
   call against the actual CRUD layer (`LLMBackedAgent` + `tools.py`) before the LLM
   answers — e.g. `list_open_requisitions`, `search_suppliers`, `get_spend_summary`,
   `list_overdue_contract_obligations`. Verified 2026-07-29: there is dormant RAG/embedding
   scaffolding in the codebase (`rag_service.py`, Chroma-based) but it's dead code, never
   wired to any agent — **do not claim RAG.** The honest and arguably stronger claim:
   real-time tool-calling beats embedding retrieval here because operational data (PO
   status, invoice match state, risk scores) changes by the minute; a vector index would
   go stale, live queries don't.

3. **Architecture benefit.** This is why judges should read it as deliberate: every
   agent call is logged (tool used, plan, explanation, latency, success) to an audit
   trail visible in the Agent Activity dashboard (`/dashboard/agent-activity`) — this is
   what turns "we added a chatbot" into "AI making verifiable decisions in production."
   [Add 1-2 sentences on why grounded-tool-calling + audit logging specifically, vs. a
   generic chat-over-your-data bolt-on.]

4. **Why Vertex AI/Gemini, specifically.** Say both halves: it satisfies the "must use a
   Google Cloud product" track requirement (this is the documented reason in the code
   comment, own it rather than omit it), *and* it keeps AI auth inside the same
   IAM/service-account boundary as the rest of the GCP stack (Cloud Run, Cloud SQL) — no
   separate API keys to manage or leak.

*For the 3-min video: compress the above four points to one line, then cut to the live
demo. Save the full version for this written narrative.*

## AI day-to-day usage

[Fill in: concrete example(s) of an agent being queried in the live product — screenshot
or transcript from the Agent Activity dashboard. Pull from real usage once the P2P smoke
test (task #3) and early customer usage generate traffic — don't backfill/stage this.]

## Human vs. AI division of labor

[Fill in: what a human still approves/decides (e.g. PO approval, budget threshold,
contract sign-off) vs. what the agent surfaces/recommends. Frame as AI operating the
business, human retaining judgment on money/risk decisions.]

## Jobs / economic opportunity created

[Fill in once customer outreach (task #4) lands: e.g. a small business that previously
needed a dedicated procurement hire can now run sourcing/PO/AP with existing staff plus
S2PNexus; any contractor/freelance work created building or supporting deployments,
if applicable.]

## The build story

[Fill in: solo/small-team build, Claude + Copilot split (Claude for architecture/fixes/
review, Copilot for primary feature builds — see [[feedback_s2pnexus_dev_pattern]]),
timeline from first commit to production. Keep this honest and specific — judges can
tell a generic AI-boosterism paragraph from a real one.]

## Facts verified and ready to cite (don't re-derive)

- All 12 domain agents grounded in real tool calls since the initial commit, live on
  Cloud Run revision 00038 as of 2026-07-29 — see [[project_s2pnexus_all_12_agents_grounded]].
- Agent Activity dashboard shipped and deployed 2026-07-27, live at `/dashboard/agent-activity`.
- Vertex AI (`AI_PROVIDER=gemini`, `GOOGLE_CLOUD_PROJECT=s2pnexus`) is the default provider
  in production, not a fallback. Cloud Run hosts backend + frontend (second GCP product).
- No RAG in production — grounding is 100% real-time tool-calling. Do not claim RAG.
- Revenue/customers: none yet as of 2026-07-28 (see `docs/XPRIZE_SUBMISSION_PLAN.md`) —
  this section can't be written honestly until task #4 lands a real customer.
