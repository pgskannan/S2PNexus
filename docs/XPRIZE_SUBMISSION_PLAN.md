# Build with Gemini XPRIZE — S2PNexus Submission Plan

Prepared 2026-07-24. Submissions close **August 17, 2026, 1:00pm PDT** (24 days out).
Judging runs Aug 20 – Sep 15; winners announced Sep 25.

Category: **Small Business Services** — S2PNexus is procurement/sourcing/contract/spend
tooling that gives small and mid-size businesses the sourcing and spend-control
capabilities normally reserved for enterprises with dedicated procurement teams.

## 1. What the rules actually require

Beyond "build something with Gemini," judging is explicitly on three things, in this
order of practical difficulty for us:

1. **Business viability** — real users, real revenue, sustainable model. This is the
   hard part: as of today there are no paying customers.
2. **AI-native operations** — the business must be *operated* by AI agents, not just
   feature-flagged with an AI chatbot. Judges look at agent execution logs, API usage,
   dashboards — evidence the agents are making real decisions in production.
3. **Category impact** — does this meaningfully move the needle for small business
   procurement, or reach credible adoption scale.

Hard requirements, not optional: the business must run on AI agents, and must use at
least one Google Cloud product.

## 2. Technical status

| Requirement | Status |
|---|---|
| Google Cloud product in the stack | **Done today.** `backend/app/ai/providers/gemini.py` now implements a real Vertex AI-backed provider (`GOOGLE_CLOUD_PROJECT` set → routes through `{location}-aiplatform.googleapis.com`, OAuth2 via Application Default Credentials). Falls back to the plain Gemini API key for local dev only. Config added in `.env.example` (`AI_PROVIDER=gemini`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GEMINI_MODEL`). `AIGatewayService` now defaults to Gemini instead of Ollama. Verified: provider factory returns the right type, health-check degrades gracefully without credentials, existing `test_provider_strategy.py` contract untouched. |
| Agents grounded in real tool calls | **Done** (per prior sprint work) — 5 of 12 domain agents (Procurement, Supplier, Contract, Sourcing, SpendAnalysis) call real CRUD through `tools.py` and go through the LLM. 7 remain placeholder-only (document, knowledge, reporting, receipt, supplier-risk, contract-authoring, contract-risk). |
| Production deployment | **Not started.** Everything currently runs locally/docker-compose. Judges need a live, reachable product. |
| Agent execution logs / audit trail visible externally | **Partial.** `AgentQueryResponse` already returns `plan` and `explanation` fields per call — good raw material. No persistent, judge-facing log/dashboard yet. |
| GCP project + billing account | **Not started.** Needed before Vertex AI calls will actually succeed (currently correctly reports "credentials not found" — that's expected until a project + service account exist). |

### Immediate technical to-dos (before anything customer-facing)
1. Create a GCP project, enable the Vertex AI API, create a service account with
   `roles/aiplatform.user`, set `GOOGLE_CLOUD_PROJECT` / `GOOGLE_APPLICATION_CREDENTIALS`
   in the deployment environment.
2. Deploy backend + frontend somewhere judges can reach without a local setup — Cloud
   Run is the obvious choice since it doubles as *another* Google Cloud product in the
   stack and removes any doubt about the requirement.
3. Add a simple "Agent Activity" log/dashboard (even a read-only table view of agent
   calls with timestamp, tool used, decision made) — this is what turns "we called an
   LLM" into visible evidence of AI-native operations for judges.
4. Decide whether to close the remaining 7 placeholder agents or leave them — not
   required, but each additional grounded agent strengthens the "AI-native operations"
   score.

## 3. The real constraint: revenue and customers in ~3 weeks

This is the part no amount of engineering solves — it needs actual outreach. Given the
product (procurement/sourcing automation), the fastest realistic path to a *real* paying
customer is not a cold broad launch, it's:

- **Target 3-5 small businesses you or your network already have warm access to** —
  ideally ones that currently do sourcing/PO/supplier management by spreadsheet or email.
  Small manufacturers, clinics, agencies, or nonprofits with a part-time ops person are
  typical buyers.
- **Price low and simple for the hackathon window** — e.g. a flat monthly fee or a
  one-time setup fee is enough to generate real Stripe revenue evidence; the amount
  matters less than it being real, disclosed, and tied to an identifiable customer.
- **Get to a signed customer (even $50-200 MRR) in the first 10 days**, not the last few —
  revenue evidence and testimonials take time to collect and judges will discount
  anything that looks backfilled in the final 48 hours.
- Consider whether S2PNexus should be **incorporated** (rules ask for a corporate ID "if
  available" — not required, but strengthens viability scoring).

## 4. Submission checklist (map to Devpost requirements)

- [ ] GitHub repo shared with **testing@devpost.com** and **judging@hacker.fund** (public or private is fine)
- [ ] 3-minute video demonstrating AI live in production making key decisions
- [ ] Written narrative, 500-1000 words: AI day-to-day usage, human vs. AI division of labor, jobs/economic opportunity created, the build story
- [ ] Revenue evidence: Stripe export or bank statement + P&L ([template](https://docs.google.com/spreadsheets/d/1pAJrEMo7_QID6V62sA4C8XwGBHkxDTVX3wtYNE2fulI/edit))
- [ ] Corporate ID, if one exists
- [ ] Expenses disclosure in the P&L, including marketing/customer-acquisition spend — **must be disclosed even if $0**
- [ ] Product evidence: agent execution logs, API usage records, dashboard screenshots
- [ ] Customer evidence: name/email/phone of real customers, testimonials/feedback
- [ ] Register the team on Devpost (xprize.devpost.com) if not already done

## 5. Suggested timeline (24 days)

**Week 1 (Jul 24-30) — unblock the hard requirements**
GCP project + Vertex AI live end-to-end; deploy to Cloud Run; identify and start
outreach to the first 3-5 target customers; register on Devpost.

**Week 2 (Jul 31-Aug 6) — first revenue + agent visibility**
Close first paying customer(s); ship the agent-activity log/dashboard; start
collecting product evidence (screenshots, logs) as you go, not retroactively.

**Week 3 (Aug 7-13) — depth and evidence**
Add/close remaining domain agents if time allows; expand to 2-4 more customers;
draft the written narrative and start filming the demo video; assemble the P&L.

**Final days (Aug 14-17) — package and submit**
Finalize video, narrative, revenue/expense evidence, customer contacts; share the
repo with the two required emails; submit before 1:00pm PDT Aug 17 (build in a buffer —
don't submit at the deadline).

## 6. Biggest open risk

Everything technical is tractable in the time available. The single thing that can sink
this submission is not having *real, verifiable* customers and revenue by the judging
window — that has to start this week, in parallel with the technical work, not after it.
