# Build with Gemini XPRIZE — S2PNexus Submission Plan

Updated 2026-07-28 (originally prepared 2026-07-24). Submissions close **August 17, 2026,
1:00pm PDT (20 days out)**. $2,000,000 total prize pool; category prize is $50,000
(Small Business Services), and every submission is also eligible for the overall
1st-5th place ($500k/$200k/$100k/$100k/$100k) and 15 Runner-Up ($50k) prizes. Confirmed
against the live rules at xprize.devpost.com on 2026-07-28 — unchanged from the 7/24 read.

**Scope decision, 2026-08-11:** with 6 days left and no realistic path to real revenue,
Kannan decided to submit **with reduced scope** rather than chase Section 5's revenue
push — skip customer outreach entirely, disclose $0 revenue honestly in the P&L, and lean
on the genuinely strong AI-native-ops evidence (12 grounded agents, Agent Activity
dashboard) instead. Effort now goes to the [[project_s2pnexus_agentic_hackathon_plan]]
build instead, which has more runway (deadline Aug 31) and was moved up to start Aug 11.
Remaining XPRIZE work: the Section 3 smoke test (bounded, cheap, still worth doing) plus
video/narrative/P&L — no further revenue-chasing.

Category: **Small Business Services** — S2PNexus is procurement/sourcing/contract/spend
tooling that gives small and mid-size businesses the sourcing and spend-control
capabilities normally reserved for enterprises with dedicated procurement teams.

## 1. What the rules actually require

Judging is on three things, in this order of practical difficulty for us:

1. **Business viability** — a real business launched in the 90-day window, with real
   users and real revenue. This is the hard part: as of today there are still no paying
   customers, unchanged since 7/24.
2. **AI-native operations** — the business must be *operated* by AI agents, not just
   feature-flagged with an AI chatbot. Judges look at agent execution logs, API usage,
   dashboards — evidence agents are making real decisions in production. This is now
   strong (see below).
3. **Category impact** — does this meaningfully move the needle for small business
   procurement, or reach credible adoption scale.

Hard requirements, not optional: the business must run on AI agents, and must use at
least one Google Cloud product. Both are met today.

## 2. Technical status (as of 2026-07-28)

| Requirement | Status |
|---|---|
| Google Cloud product in the stack | **Done, live.** Vertex AI (`AI_PROVIDER=gemini`, `GOOGLE_CLOUD_PROJECT=s2pnexus`) is the default provider in production, not just a dev fallback. Cloud Run hosts both backend and frontend — a second GCP product in the stack. |
| Production deployment | **Done.** Backend + frontend both live on Cloud Run, reachable without any local setup. |
| Agents grounded in real tool calls | **All 12 of 12 domain agents** call real CRUD through `tools.py` and go through the LLM — corrected 2026-07-29, this has been true since the initial commit (confirmed via `git log` + live on Cloud Run rev 00038); the earlier "5 of 12" figure recorded here was wrong. No further grounding work needed. |
| Agent execution logs / audit trail visible externally | **Done, live.** Agent Activity dashboard (`/dashboard/agent-activity`) shipped and deployed 2026-07-27 — persists every agent call (tool used, plan, explanation, latency, success) with a filterable, paginated judge-facing view plus a summary/aggregate endpoint. This was the single highest-leverage AI-native-ops gap from the 7/24 plan and is now closed. |
| End-to-end Procure-to-Pay flow | **Deployed.** Confirmed 2026-08-09: backend rev `00106-wmg` (2026-08-06 13:52 UTC) and frontend rev `00084-wcw` (2026-08-06 02:14 UTC) both healthy, 100% traffic, and include every commit through `c38f493` — all 52 migrations (incl. the Aug 4 batch) applied via `alembic upgrade head` on container start. Remaining gap: no single unscripted smoke test has walked the full chain live — see Section 3, action item 2. |
| Supplier Lifecycle (upstream) | **Live, simple end-to-end.** Request → Registration → Qualification/Risk/Approval → Supplier → active/under_monitoring/requalification/offboarding states, plus hierarchy + duplicate-merge, all deployed with UI. This is a real, demoable upstream flow today. |

## 3. Top priority: one fully deployed, fully verified end-to-end P2P flow

This is the specific gap the plan is now built around. The enterprise-grade P2P rebuild
(`docs/COPILOT_ENTERPRISE_PROCUREMENT_PROMPT.md`, Phases 0-5) is **built and committed**
but **never deployed together**, and no single test has walked the entire chain start to
finish against the live system. Nine chained, dry-run-verified Alembic migrations are
sitting undeployed:

document numbering → commodity codes/GL mapping (Phase 0) → address book (Phase 1) →
PO line items/shipping/GL auto-populate (Phase 2) → goods receipt line items + over-receipt
detection (Phase 3) → invoice line items + real 2-/3-way matching + exceptions (Phase 4) →
split accounting + hard/soft budget enforcement (Phase 5) → GL accounts master data →
PR-to-PO conversion + PO list/detail UI + AI gateway default grounding prompt.

In other words: the "one full end-to-end P2P process" the submission needs largely
**already exists in code** —

**Requisition (line items, commodity autocomplete) → Approval → Convert to PO
(ship-to/bill-to, GL auto-populate, shipping allocation) → Goods Receipt (partial/full,
over-receipt exceptions) → Invoice + 2-/3-way match (exceptions worklist) → live Budget
committed/actual check on PO approval**

— it just hasn't been (a) deployed as one coherent stack, or (b) walked start-to-finish
in the live environment. That single verified walkthrough is exactly what the 3-minute
demo video needs, so closing this gap and filming it can be nearly the same activity.

**Action items:**
1. ~~Apply all 9 undeployed migrations to prod Postgres in order, redeploy backend +
   frontend to Cloud Run~~ — **done**, confirmed deployed 2026-08-09 (see status table above).
2. Run one real, unscripted smoke test against the live deployment covering the full
   chain above, including at least one exception path (an over-receipt, a matching
   variance) to show the AI/workflow layer actually adjudicating something, not just a
   happy path. **Still open — this is now the top remaining technical gap.**
3. Confirm the Agent Activity dashboard captures real calls generated by this flow
   (procurement-agent tool calls specifically), not just supplier/sourcing traffic.
4. Given Kannan is near his weekly Claude usage cap (resets 2026-07-29 14:00): default to
   Copilot for any last-mile fixes the smoke test surfaces; use Claude for the deploy
   sequencing/migration ordering itself and for reviewing whatever Copilot produces,
   consistent with the established build split on this project.

## 4. Secondary technical lever: more grounded agents — CLOSED, no action needed

Superseded 2026-07-29: all 12 agents (including `ReceiptAgent` and `SupplierRiskAgent`,
named here as candidates on 7/28) are already grounded and have been since the initial
commit. This section previously tracked stale information; nothing left to do here.

## 5. The real constraint: revenue and customers in ~20 days

Unchanged from 7/24 and still the single biggest risk — no amount of engineering solves
this, it needs actual outreach, and it should be running **in parallel with, not after,**
Section 3:

- **Target 3-5 small businesses already in reach** — ones that today run PR/PO/supplier
  management by spreadsheet or email. Small manufacturers, clinics, agencies, or
  nonprofits with a part-time ops person are typical buyers.
- **Price low and simple for the hackathon window** — a flat monthly or one-time setup
  fee is enough for real Stripe revenue evidence; the amount matters less than it being
  real, disclosed, and tied to an identifiable customer.
- **Get to a signed customer (even $50-200 MRR) by ~Aug 7**, not the final week —
  revenue evidence and testimonials take time to collect, and judges will discount
  anything that looks backfilled in the last 48 hours.
- Consider incorporating S2PNexus (rules ask for a corporate ID "if available" — not
  required, but strengthens viability scoring).

## 6. Submission checklist (map to Devpost requirements)

- [ ] GitHub repo shared with **testing@devpost.com** and **judging@hacker.fund**
- [ ] 3-minute video demonstrating AI live in production making key decisions —
      build this from the Section 3 walkthrough plus the Supplier Lifecycle flow
- [ ] Written narrative, 500-1000 words: AI day-to-day usage, human vs. AI division of
      labor, jobs/economic opportunity created, the build story
- [ ] Revenue evidence: Stripe export or bank statement + P&L
      ([template](https://docs.google.com/spreadsheets/d/1pAJrEMo7_QID6V62sA4C8XwGBHkxDTVX3wtYNE2fulI/edit))
- [ ] Corporate ID, if one exists
- [ ] Expenses disclosure in the P&L, including marketing/customer-acquisition spend —
      **must be disclosed even if $0**
- [ ] Product evidence: agent execution logs, API usage records, dashboard screenshots —
      Agent Activity dashboard covers this; capture screenshots on an ongoing basis, not
      retroactively
- [ ] Customer evidence: name/email/phone of real customers, testimonials/feedback
- [ ] Confirm team registration on Devpost (xprize.devpost.com)

## 7. Timeline (20 days, Jul 28 → Aug 17 1:00pm PDT)

**Days 1-3 (Jul 28-30) — close the P2P deployment gap**
Apply the 9 pending migrations, redeploy backend + frontend, run the full end-to-end
smoke test from Section 3 including an exception path. This becomes the demo video's
backbone. In parallel: start outreach to the first 3-5 target customers, confirm Devpost
registration.

**Days 4-10 (Jul 31-Aug 6) — first revenue + evidence collection**
Close first paying customer(s) — target by Aug 7. Start capturing Agent Activity
dashboard screenshots/exports as real traffic accumulates. Optionally ground 1-2 more
placeholder agents (Section 4) if time allows.

**Days 11-16 (Aug 7-13) — depth and packaging**
Expand to 2-4 more customers if possible. Draft the written narrative. Start filming the
demo video. Assemble the P&L with revenue and expense disclosure.

**Days 17-20 (Aug 14-17) — finalize and submit**
Finalize video, narrative, revenue/expense evidence, customer contacts. Share the repo
with both required emails. Submit with a real buffer before 1:00pm PDT Aug 17 — do not
submit at the deadline.

## 8. Biggest open risk (unchanged)

Everything technical is now tractable well within the time available — the P2P
deployment gap in Section 3 is a known, bounded amount of work, not a design problem.
The one thing that can still sink this submission is not having *real, verifiable*
customers and revenue by the judging window. That has to be running now, in parallel,
not queued behind the technical work.
