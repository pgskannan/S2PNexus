# Prompt for Fable 5 — Universal Template Framework (via Supplier Request) + Preferred Supplier Framework

Written 2026-08-02, against `docs/S2P NEXUS – UNIVERSAL TEMPLATE FRAMEWORK SPECIFICATION`
(pasted by Kannan, not yet a repo file — paste the spec itself alongside this prompt).
Scope confirmed with Kannan: target modules are the **Universal Template Framework core**
(spec Sections 4-12), proven out on **Supplier Request** (the SLP intake step, spec's own
first-listed Ariba pain point), and the **Preferred Supplier Framework** (spec Section 17).
Qualification, Risk, and Performance are explicitly *not* being built as full modules in
this batch — they're stubbed with real-data proxies just far enough to feed the Preferred
Supplier composite score. Flag, don't silently expand, if a later phase seems to require
building one of them out for real.

**Repo audit before writing this prompt (2026-08-02), so Fable 5 doesn't re-discover it at
the cost of a turn:**
- No template/questionnaire/scoring engine exists anywhere in the codebase. `grep -ril
  "template\|questionnaire\|qualification\|preferred"` across `backend/app/models/` hits
  only `ContractTemplate` (static boilerplate text, `models/contract_lifecycle.py:61` —
  unrelated to dynamic questionnaires) and unrelated string fields
  (`preferred_payment_method`, `preferred_region`).
- `SupplierRequest` (`backend/app/models/supplier_request.py`) is a fixed-column
  SQLAlchemy model — title, business_justification, commodity_categories,
  estimated_annual_spend, diversity_required, risk_justification, etc. — with **no
  frontend at all** (confirmed: no file under `frontend/` references it) and
  `crud/supplier_request.py`'s `transition_supplier_request()` (line 102) flips
  `status`/`approval_status` directly with a hardcoded action map — it never calls the
  workflow engine. This is the exact "hard-coded templates, no conditional approval
  routing" pain point the spec calls out for SLP in Section 2, confirmed true today, not
  hypothetical.
- Real, already-live data exists for three of the four Preferred Supplier score inputs:
  risk (`SupplierRegistration.risk_score`/`risk_level`, `models/supplier_registration.py:60-61`,
  set once at intake), spend (`crud/analytics.py`'s `get_supplier_analytics()`, already
  aggregates spend per supplier), and performance proxies (`GoodsReceipt.has_exceptions`
  and `ProcurementInvoice.match_status` from the already-deployed Phase 3/4 P2P work,
  `crud/procurement.py`). **Qualification has no real data source at all** — spec Section 16
  is a full module this batch doesn't build; Phase 2 below adds a minimal placeholder
  record for it and says so explicitly.
- Two engines already exist and must be reused, not duplicated: the **workflow engine**
  (`WorkflowDefinition`/`WorkflowInstance`/`WorkflowTask`, `crud/workflow.py`) and the
  **approval matrix engine** (`ApproverSeed`, `crud/approval.py`'s
  `resolve_approvers_for_context()`, role codes in `models/approval.py:26` — currently
  `MANAGER, MANAGER_MANAGER, DEPT_HEAD, CFO, FIN_CTRL, PROC_HEAD, AP_HEAD, AP_PROCESSOR`,
  no Category Manager / Risk Team / Compliance Team codes yet). See
  `docs/FABLE5_WORKFLOW_MANAGEMENT_PROMPT.md` for the conventions those two engines already
  follow — don't relitigate them.

---

## Context for every phase (paste once)

You are extending S2PNexus, a Next.js (App Router) + FastAPI/SQLAlchemy async/Pydantic v2
codebase. Paste the full Universal Template Framework spec alongside this file — phases
below cite spec section numbers rather than re-quoting them.

**Backend conventions**: async SQLAlchemy 2.0 style (`Mapped`/`mapped_column`), Pydantic v2
schemas in `backend/app/schemas/`, CRUD in `backend/app/crud/`, routers in
`backend/app/routers/`. One Alembic head — run `alembic heads` before writing a new
migration, and chain onto whatever is actually current (check `git log --oneline -- backend/alembic/versions` — several migrations from late July are still undeployed per project
memory, don't assume prod matches HEAD). Tenant scoping: every new table needs `tenant_id`
and every query must filter by it, matching `list_approver_seeds()`'s pattern in
`crud/approval.py`. Async tests: real-DB integration style in `tests/integration/` (plain
`def test_x(): asyncio.run(...)`), not `pytest-asyncio` fixtures — if you need
`pytest-asyncio` at all, pin `0.23.8`, not the `0.23.3` in requirements.txt (sandbox-specific
known issue).

**Frontend conventions**: pages under `frontend/app/dashboard/...`, `<div className="card">`,
`btn-primary`/`btn-secondary`/`input-field`/`label` utility classes — don't invent new
component styling. Admin-only screens go under `frontend/app/dashboard/admin/...`
(auto-wrapped by `admin/layout.tsx`), gated client-side on `user?.role === "administrator"`
with a read-only fallback view for non-admins, never a hidden page. All API calls through
typed wrappers in `frontend/lib/api.ts`; new shapes into `frontend/lib/types.ts`.

**Do not build**: a generic drag-and-drop template *designer* UI in this batch. Templates
are authored as JSON (seed scripts / admin JSON editor is enough for now) — the payoff here
is the runtime engine (dynamic rendering, scoring, conditional routing), not an authoring
UX. Flag if you think the authoring UX is actually required to demo this; don't build it
speculatively.

---

## Phase 0 — Universal Template Framework core (minimal, real, generic)

Goal: the data model and runtime from spec Sections 4-9, scoped to what Phase 1 (Supplier
Request) actually needs — not the full 20-section spec in one shot.

**Models** (new file `backend/app/models/template.py`):
- `TemplateDefinition`: id, tenant_id (nullable = global), module (`FreeText` matching spec
  Section 5's list: `supplier_request`, `slp`, `qualification`, `risk`, `performance`,
  `sourcing`, `contracts`), name, version (int), status (`draft|published|deprecated`),
  effective_date, expiry_date, inheritance_mode (`global|tenant|local`, default `global`).
  Only `global → tenant` override matters for this batch — skip `local` scoping logic,
  flag it as a gap rather than half-implementing it.
- `TemplateSection`: id, template_id FK, name, order, visibility_rule (JSON, spec Section 8
  shape — a small condition tree: `{"field": "...", "op": "eq|neq|gt|lt|in", "value": ...}`
  with optional `all`/`any` nesting), mandatory_flag.
- `TemplateQuestion`: id, section_id FK, question_type (spec Section 6's list — implement
  `text, textarea, numeric, date, yes_no, dropdown, multiselect, file_upload` for this batch;
  `table_grid`, `kpi_input`, `clause_selector`, `ai_generated` are out of scope, stub the enum
  value but don't build renderers for them), question_text, help_text, default_value,
  editable_flag, visible_flag, mandatory_flag, scoring_rule (JSON, spec Section 7 shape:
  `{"weight": 0-100, "map": {"answer_value": score_0_10}}` for choice types, or
  `{"weight": ..., "threshold": ...}` for numeric), dependencies (parent_question_id +
  same visibility_rule shape), order.
- `TemplateResponse` (one row per submission instance, not per question — store answers as
  a JSON blob keyed by question_id): id, template_id FK, entity_type, entity_id (the
  polymorphic link — e.g. `supplier_request`, the request's id), answers (JSON), computed_score,
  computed_grade, submitted_by, submitted_at, tenant_id.

**Engine** (`backend/app/services/template_engine.py`):
- `evaluate_visibility(rule, answers) -> bool` — evaluates a `TemplateSection`/`TemplateQuestion`
  visibility_rule against a submitted-so-far answers dict. Reuse the condition-evaluation
  *shape* already proven in `crud/workflow.py`'s `_evaluate_condition()` /
  `_coerce_numeric()` (numeric comparisons on stringified Decimal context values are a known
  footgun there — read that function before writing this one, don't reintroduce the bug it
  fixed).
- `score_response(template, answers) -> (score: float, grade: str)` — walks all questions,
  applies each `scoring_rule` weight, sums to a 0-100 composite, maps to A-F per spec
  Section 7's exact bands (A 90-100, B 80-89, C 70-79, D 60-69, F <60).
- `get_effective_template(db, module, tenant_id) -> TemplateDefinition` — spec Section 4's
  inheritance: tenant-specific published template if one exists for `module`, else the
  global published one. This is the one piece of "tenant override" logic actually needed.

**Tests**: unit tests for `evaluate_visibility` (nested all/any, numeric threshold, parent=Yes
cases from spec Section 8's examples) and `score_response` (grade boundary cases) — pure
functions, no DB needed for these two.

---

## Phase 1 — Supplier Request becomes template-driven

Goal: replace `SupplierRequest`'s fixed-column pain point with a real dynamic form, without
breaking the existing rows/API contract that may already have data in it.

**Do not drop or rename existing `SupplierRequest` columns.** Keep `title`,
`requestor_id`, `status`, `lifecycle_status`, `approval_status` as first-class columns (the
system needs them regardless of template content). Move the rest — business_justification,
commodity_categories, suggested_supplier_name, existing_supplier_check, preferred_region,
estimated_annual_spend, diversity_required, risk_justification — into a `TemplateResponse`
row (`entity_type="supplier_request"`, `entity_id=<request.id>`) against a seeded
`TemplateDefinition(module="supplier_request")` whose questions mirror those exact fields
one-for-one, so existing data isn't lost — write a small migration/backfill script that
creates one `TemplateResponse` per existing `SupplierRequest` row from its current column
values, then add the new dynamic questions (below) as template-only, no matching column.

**New dynamic behavior this actually buys you** (don't skip this — it's the point of the
exercise, not decoration):
- Conditional section per spec Section 8: `diversity_required = Yes` → show a
  "Diversity Certification Upload" question (file_upload type); `risk_justification` filled
  in → show a "Risk Mitigation Plan" question. Today both fields exist unconditionally in
  the fixed schema regardless of relevance.
- Scoring: a lightweight "request completeness/risk flag" score (spec Section 7) — not a
  hard gate, just computed and stored on the `TemplateResponse`, surfaced to reviewers.
- Conditional approval routing (spec Section 9), replacing `transition_supplier_request()`'s
  hardcoded action map: `diversity_required = Yes OR risk_justification non-empty` → route
  through the workflow engine to Compliance before approval, instead of `PROC_HEAD` alone.
  This is the single clearest fix to the "no conditional approval routing" gap confirmed in
  the audit above — implement it via the workflow engine (Phase 4 below), not a second
  hand-rolled if/else ladder next to the one you're replacing.

**Backend**: `POST /suppliers/requests` keeps its existing required fields for backward
compatibility but also accepts an `answers` dict for the new dynamic questions; `GET` returns
both the system fields and the resolved `TemplateResponse` (questions + answers + visibility
already evaluated, so the frontend doesn't re-implement the engine).

**Frontend**: `frontend/app/dashboard/suppliers/requests/new/page.tsx` (net new — no
supplier-request UI exists today, confirmed in the audit). Build one generic
`<DynamicTemplateForm templateId=... entityType=... onSubmit=...>` component in
`frontend/components/` that renders sections/questions from `GET /templates/{module}/effective`
and re-evaluates visibility client-side on every answer change (mirror
`evaluate_visibility`'s logic exactly — don't invent a second condition grammar). This
component is deliberately reusable — Phase 5 wires it into a second screen without
modification.

**Tests**: integration test — submit a request with `diversity_required=true`, assert the
diversity question's `TemplateResponse` answer is required-and-present, assert it routes to
Compliance not just `PROC_HEAD`.

---

## Phase 2 — Preferred Supplier score inputs (real where data exists, flagged where it doesn't)

Goal: four inputs for the Section 17 composite formula. Three are computed from data that
already exists; one is a new, explicitly-labeled placeholder.

- **Risk (real)**: add `current_risk_score`/`current_risk_level` to `Supplier`
  (`models/supplier.py`), backfilled from the linked `SupplierRegistration.risk_score` at
  conversion time (find the registration→supplier conversion code path — likely in
  `crud/supplier_registration.py` or `services/supplier_workflow.py` — and set it there).
  Admin-editable via the existing supplier update endpoint. This is *not* the full Supplier
  Risk module from the spec (weighted multi-factor scoring, external data integration) —
  it's a live mirror of the one number that already exists. Say so in a code comment.
- **Performance (real, derived)**: new `compute_supplier_performance_score()` in
  `crud/analytics.py` (next to `get_supplier_analytics()`) — trailing 90-day window,
  weighted from data that's actually live: `(1 - goods_receipt_exception_rate) * 0.5 +
  (1 - invoice_match_exception_rate) * 0.5`, scaled to 0-100. Read `GoodsReceipt.has_exceptions`
  and `ProcurementInvoice.match_status` query patterns already used in
  `crud/procurement.py`'s `get_invoices_with_open_exceptions()` (line ~1544) rather than
  re-deriving the exception logic. Suppliers with zero receipts/invoices in the window get
  `None`, not a fabricated default — the composite formula (Phase 3) needs to handle a
  missing component.
- **Spend Tier (real, derived)**: bucket `get_supplier_analytics()`'s trailing spend total
  into tiers 1-4 via configurable thresholds (a `SystemSetting` row per
  `models/system_setting.py`'s existing pattern, not a hardcoded constant — tenants will
  have very different spend scales).
- **Qualification (placeholder, flagged)**: new minimal `SupplierQualification` model
  (supplier_id, score 0-100, grade A-F, status, valid_until, updated_by, updated_at) —
  manually set by a category manager via a small admin form, *not* the full
  Template-Framework-driven qualification questionnaire from spec Section 16. Name the
  model and its docstring explicitly as a placeholder standing in for that future module, so
  nobody mistakes this for Section 16 being done.

**Tests**: unit test for `compute_supplier_performance_score()` with known
exception-rate fixtures; assert `None` (not 0) when there's no receipt/invoice history.

---

## Phase 3 — Preferred Supplier composite engine

Goal: spec Section 17's exact formula and thresholds, computed on demand.

**Model**: `PreferredSupplierStatus` (supplier_id FK, preferred_status
[`preferred|strategic|approved|blocked|none`], composite_score, category, region,
spend_tier, qualification_score, performance_score, risk_score, computed_at,
override_flag, override_by, override_reason, tenant_id).

**Engine** (`backend/app/services/preferred_supplier.py`):
- `compute_preferred_score(inputs) -> float`: `0.30*qualification + 0.30*performance +
  0.20*(100 - risk_score) + 0.20*spend_tier_normalized`. Note the explicit inversion on
  risk — the spec's raw formula (`0.20 * Risk`) only makes sense if "Risk" there means an
  inverted risk-favorability score, not the raw risk_score where higher = worse; implement
  the inversion and comment why, don't transcribe the formula literally and produce a
  composite score that rewards high risk.
- If qualification_score is `None` (Phase 2's placeholder never set), exclude it from the
  weighted average and re-normalize the remaining weights rather than treating it as 0 —
  a supplier with no qualification record yet shouldn't be auto-blocked by omission.
- Thresholds exactly per spec: Preferred ≥85, Strategic ≥90 **and** has an active contract
  (`Contract.status`/`lifecycle_status` for that supplier_id — query `models/contract.py`,
  don't add a duplicate "has_contract" boolean to Supplier), Approved ≥70, Blocked <60 **or**
  risk_score >80 (the OR matters — a high-risk supplier with a decent composite still gets
  blocked).
- Auto-preferred / auto-block per spec Section 17's exact bullet conditions.
- `POST /suppliers/{id}/preferred/recompute` (single) and a batch admin endpoint — this is
  the only trigger for this batch. Don't wire a web of on-change hooks (qualification
  update, new contract, new sourcing award) that fire recompute automatically — that's a
  reasonable v2, but multiplies the surface area for this batch with no demo payoff over an
  explicit recompute button/endpoint.

**Tests**: unit tests covering every threshold boundary (84.9 vs 85, the Strategic
contract-coverage AND, the Blocked OR), and the qualification-is-None re-normalization case.

---

## Phase 4 — Workflow wiring (reuse the engine, don't duplicate it)

Goal: both Phase 1's conditional Supplier Request routing and Phase 3's borderline/override
Preferred Supplier changes go through the existing workflow + approval-matrix engines.

- Add role codes to `APPROVER_ROLE_CODES` (`models/approval.py:26`) only for roles that
  genuinely don't map onto an existing one: `CATEGORY_MGR`, `RISK_TEAM`, `COMPLIANCE`. Map
  spec's "Procurement Director" onto the existing `PROC_HEAD` — don't add a duplicate code
  for the same role under a different name.
- Supplier Request: follow the exact pattern in `services/supplier_workflow.py`'s
  `start_supplier_requalification_workflow` (`entity_type="supplier"` lookup, build context,
  `start_workflow_instance`) — replicate it for `entity_type="supplier_request"`, called
  from `transition_supplier_request()` on `submit` instead of the current direct
  `approval_status = "pending"` flip. If no `WorkflowDefinition` exists for
  `entity_type="supplier_request"` yet, fall back to today's behavior unchanged (zero
  regression for tenants with nothing configured — same fallback contract as every other
  workflow integration in this codebase) and seed one default definition (mirrors
  `PROC_HEAD` approval, with a `COMPLIANCE` branch gated on the same condition described in
  Phase 1) in `backend/scripts/seed_approver_matrix.py` next to the existing seeds.
- Preferred Supplier: auto-preferred/auto-block (Phase 3) bypass the workflow entirely —
  spec explicitly allows auto-classification. Only a manual override or a borderline
  Strategic/Approved change routes through `entity_type="preferred_supplier_review"`,
  context = category/risk/composite score, approvers = `CATEGORY_MGR → PROC_HEAD →
  RISK_TEAM → COMPLIANCE` per spec Section 17's workflow list.

**Tests**: integration test per routing path — a diversity-flagged supplier request reaches
a `COMPLIANCE`-role task; a manual Preferred override starts an instance that resolves
through all four roles in order.

---

## Phase 5 — Frontend surfacing

- `frontend/app/dashboard/suppliers/requests/new/page.tsx` from Phase 1, using the shared
  `<DynamicTemplateForm>`.
- New `frontend/app/dashboard/admin/preferred-suppliers/page.tsx`: table of
  `PreferredSupplierStatus` — status, composite score with the four-component breakdown,
  category, region, filters by status/category/region, manual override control (admin-only,
  requires a reason, calls `POST /suppliers/{id}/preferred/recompute` or a
  `PATCH .../override`). Add typed wrappers to `lib/api.ts` and shapes to `lib/types.ts`.
- Supplier detail page: a Preferred Supplier badge/panel (status + score breakdown) —find
  the existing supplier detail page pattern before adding a new one from scratch.
- Sourcing hook (spec Section 18): when building a `SourcingEventInvitation` list, surface
  preferred/strategic suppliers first and flag non-preferred selections as requiring
  justification — read the actual sourcing-event creation flow in
  `frontend`/`backend/app/routers/sourcing.py` first; this is a UI nudge, not a hard gate.
- Contract hook (spec Section 18): a warning banner on the supplier detail page if
  preferred/strategic without an active `Contract` — a visible flag, not an enforcement
  block (nothing elsewhere in the codebase blocks on this, don't introduce the first one
  here without an explicit ask).

**Tests**: `tsc --noEmit` and `next build` clean (per project convention, sandbox can't run
these — manual review if building outside a environment with `next build` access).

---

## Definition of done (all phases)

- Submitting a Supplier Request with `diversity_required=true` shows a certification-upload
  question that wasn't visible before, and routes to Compliance — not just `PROC_HEAD` —
  without any code change to add a new supplier-request type.
- The same `<DynamicTemplateForm>` component that renders the Supplier Request form could
  render a second module's template (e.g., a hypothetical future Qualification form) by
  pointing it at a different `module` value — prove this isn't Supplier-Request-specific by
  keeping all Supplier Request field names out of the generic component.
- `GET /suppliers/{id}` (or a new endpoint) shows a Preferred Supplier composite score built
  from real risk/performance/spend data plus the flagged Qualification placeholder, with the
  exact spec Section 17 thresholds enforced.
- A borderline Preferred Supplier change requires sign-off from Category Manager →
  Procurement Director → Risk Team → Compliance, routed through the existing workflow
  engine — no parallel routing logic.
- Existing `SupplierRequest` rows and their data survive the migration to
  `TemplateResponse`-backed answers with no data loss.
- Per this batch's explicit scope: no Qualification questionnaire, no Risk module, no
  Performance module, and no template-designer UI were built — if any of these crept in,
  flag it rather than quietly shipping scope creep.
