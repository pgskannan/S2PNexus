# Prompt for Fable 5 — Supplier Type & Excel-Based Registration Framework

Written 2026-08-03, against `docs/SUPPLIER_TYPE_REGISTRATION_FS.md` (the full consolidated
FS Kannan pasted 2026-08-03 — paste that file's contents alongside this prompt; it's not
re-quoted here, phases below cite its section numbers). This was explicitly parked behind
XPRIZE demo work on 2026-08-03 and is now unparked — Kannan's own words: "this is a very big
differentiator."

**Read this whole prompt, including the audit section, before writing any code.** The repo
already has more relevant infrastructure than the FS assumes, and picking the wrong
foundation to build on will cost more than the time spent reading first.

---

## Repo audit before writing this prompt (2026-08-03), so Fable 5 doesn't re-discover it

**Nothing Supplier-Type-specific exists yet.** `grep -ril "supplier_type\|SupplierType"` across
`backend/app/models/` returns zero hits. No `RegistrationMode`, no configuration matrix, no
Excel import/export anywhere in the codebase.

**Two candidate foundations already exist for the Questionnaire Framework (FS Section 8) —
read both, then pick one, don't build a third:**

1. **Template Framework** (`backend/app/models/template.py`, `services/template_engine.py`,
   full admin authoring UI at `frontend/app/dashboard/admin/templates`, built 2026-08-03) —
   `TemplateDefinition`/`TemplateSection`/`TemplateQuestion`/`TemplateResponse`, with
   `evaluate_visibility()` (condition trees: field/op/value with all/any nesting) and
   `score_response()` (weighted scoring → letter grade) already implemented and live. Modules
   currently registered in `TEMPLATE_MODULES`: `supplier_request, slp, qualification, risk,
   performance, sourcing, contracts` — **no `supplier_registration` module yet**. This maps
   almost one-to-one onto FS Section 8 (question types, visibility rules, scoring rules,
   modules) and is very likely the right foundation for the Excel questionnaire content.
   **Grade-band mismatch to resolve, don't silently pick one:** this FS (Section 9) specifies
   A=90-100, B=75-89, C=50-74, D<50 (4 bands, no F). `template_engine.py`'s existing
   `score_response()` uses A 90-100, B 80-89, C 70-79, D 60-69, F<60 (5 bands) per the earlier
   Template Framework spec. Confirm with Kannan or make `score_response()` accept a
   module-specific band table rather than hardcoding one — don't let the questionnaire look
   like it's using FS bands when it's actually still on the old five-band scale.
2. **Metadata Engine** (`backend/app/metadata_engine/`, ~200 files, mounted live in
   `main.py` — not dead code) — a separate, generic, domain-agnostic custom-fields platform:
   versioned metadata objects/fields/layouts/picklists, a full expression engine (IF/AND/OR/
   CASE/SUM/LOOKUP/DATEADD etc.), dependency graph with cycle detection and impact analysis,
   outbox events. Its own README says "No Supplier-specific logic is present." This looks
   built for a different problem (generic per-tenant custom fields with computed/formula
   values across arbitrary entities) than FS Section 8's supplier-registration questionnaire.
   **Don't default to this just because it's more sophisticated** — read
   `backend/app/metadata_engine/README.md` and skim `bootstrap/definitions.py`, then make a
   deliberate call on whether any part of it (e.g. the expression engine for `ScoreFormula`
   evaluation, Section 15's field-format validation) is worth reusing for this FS versus
   building the narrower thing Template Framework already does. State the decision in a code
   comment either way.

**Supplier Request → Supplier → Registration pipeline has a real gap, not just an unwired
one:** `crud/supplier_request.py` and `services/supplier_workflow.py` handle
`SupplierRequest` creation and its approval workflow (`start_supplier_request_workflow`,
entity_type=`supplier_request` — this routing already works, built under the earlier Template
Framework prompt), but **neither ever creates a `Supplier` record.** FS Section 5.2 steps 5-6
("Supplier Creation" → "Registration Trigger") don't exist in code at all today — this isn't
a wiring gap, it's a missing step. Phase 2 below has to add it.

**`SupplierRegistration` model** (`backend/app/models/supplier_registration.py`) already has
most of FS Section 13's "Supplier Information" sheet fields — `legal_name`, `tax_id`,
`address_line1/2, city, state_province, postal_code, country`, `primary_contact_name/email`,
`banking_info` (currently one `Text` blob, not split `BankAccountNumber`/`BankRoutingNumber`
— decide whether to split it or parse the blob), `risk_score`, `risk_level`, and a
`supplier_id` FK set once approved-and-converted. Missing: `template_version`,
`questionnaire_version`, and any tamper/hash-signature field for FS Section 15.1's structural
validation. Extend this model rather than creating a parallel one.

**No Excel library and no object storage client in `backend/requirements.txt`.** FS Section
13's locked/versioned workbook and Section 16's import engine need `openpyxl` (or similar)
added, and file storage for generated/returned workbooks needs a real backend — this repo has
no S3/GCS client wired anywhere yet (the existing `ProcurementAttachment.storage_key` field
has the same gap, per `docs/PR_AUDIT_QUICK_WINS_2026-08-02.md` item 5 — flag if solving this
here should also close that older gap rather than building two separate storage integrations).

**Ad-hoc tasks (FS Section 10) map almost exactly onto the existing `WorkflowTask` model**
(`backend/app/models/workflow.py`) — `assignee_id` (AssignedTo), `due_at` (SLA),
`escalate_to` (EscalationRules), `status`, `completed_by`. Don't build a parallel
`AdHocTask` model. Decide whether ad-hoc tasks need a full `WorkflowInstance` wrapper (gets
you the existing `/workflow/tasks/{id}/complete` API and notification wiring for free) or can
be created as standalone `WorkflowTask` rows without an instance — document the choice.

**Notifications (FS Section 11) already have a real, generic model** —
`Notification` (`backend/app/models/workflow.py`, `recipient_id`, `title`, `message`,
`related_entity_type`/`related_entity_id`, `is_read`) plus a working frontend bell/list in
`Nav.tsx`. Add new events to whatever service currently creates `Notification` rows, don't
build a second notification system.

**Reuse, don't duplicate:** workflow engine (`WorkflowDefinition`/`WorkflowInstance`/
`WorkflowTask`, `crud/workflow.py`) and approval-matrix engine (`ApproverSeed`,
`crud/approval.py`'s `resolve_approvers_for_context()`) for every `ApprovalWorkflowConfig` in
the Section 17 matrix — same engines `docs/FABLE5_WORKFLOW_MANAGEMENT_PROMPT.md` and
`docs/FABLE5_TEMPLATE_AND_PREFERRED_SUPPLIER_PROMPT.md` already used. Read those two files for
the conventions (role codes, condition grammar, `_coerce_numeric` footgun) before
reimplementing anything that looks like it should already exist.

---

## Context for every phase (paste once)

You are extending S2PNexus, a Next.js (App Router) + FastAPI/SQLAlchemy async/Pydantic v2
codebase. Paste the full FS (`docs/SUPPLIER_TYPE_REGISTRATION_FS.md`) alongside this file —
phases below cite its section numbers rather than re-quoting them.

**Backend conventions**: async SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Pydantic v2 schemas
in `backend/app/schemas/`, CRUD in `backend/app/crud/`, routers in `backend/app/routers/`.
One Alembic head — run `alembic heads` before writing a migration, chain onto whatever is
actually current (`git log --oneline -- backend/alembic/versions`; several migrations are
routinely committed-but-undeployed on this project, don't assume prod matches HEAD). Tenant
scoping: every new table needs `tenant_id`, every query filters by it. `from __future__ import
annotations` + a bare `-> None` return type on a 204 endpoint crashes FastAPI's response-model
inference at import time — use explicit `response_model=None` on any no-body endpoint (this
bit production once already this week). Never use an all-zero UUID as a sentinel value —
SQLite's NUMERIC affinity corrupts it on read (irrelevant in Postgres prod, but breaks local
sandbox tests). Async tests: real-DB integration style in `tests/integration/`, pin
`pytest-asyncio==0.23.8` if you need it at all.

**Frontend conventions**: pages under `frontend/app/dashboard/...`, `<div className="card">`,
`btn-primary`/`btn-secondary`/`input-field`/`label` utility classes. Admin-only screens go
under `frontend/app/dashboard/admin/...`, gated client-side on
`user?.role === "administrator"` with a read-only fallback for non-admins. All API calls
through typed wrappers in `frontend/lib/api.ts`; new shapes into `frontend/lib/types.ts`. List
pages that can grow large should paginate client-side (10 rows/page) using the shared
`frontend/components/Pagination.tsx` (`usePagination` hook) added 2026-08-03 — don't build a
second pagination pattern.

**Do not build**: a generic drag-and-drop Excel-template designer. The Excel layout itself
(sheets, columns, locked cells) is defined in code/config per FS Sections 13-14, not authored
through a UI in this batch — the payoff is the trigger logic, import engine, and scoring, not
a visual Excel-builder. Flag if you think it's actually needed for the demo; don't build it
speculatively.

---

## Phase 1 — Supplier Type model & configuration matrix

Goal: FS Section 4 + Section 17's exact matrix, as real, queryable configuration.

**Model** (new file `backend/app/models/supplier_type.py`): `SupplierType` — id, tenant_id
(nullable = global default, matching the `TemplateDefinition` inheritance pattern), code,
name, registration_mode (`auto|manual|none`), registration_method (`excel_only` for this
batch — enum now so a future portal mode doesn't require a schema change), required_
questionnaire_modules (JSON list, e.g. `["core","tax","bank","compliance"]`),
qualification_rule (JSON condition tree, same shape as Template Framework's visibility_rule
so you're not inventing a second condition grammar), preferred_supplier_rule (same shape),
ad_hoc_task_templates (JSON list of task-type codes), notification_rule (JSON: sla_days,
reminder_at_days, escalation_at_days), approval_workflow_config (ordered list of role codes —
resolve against `APPROVER_ROLE_CODES`, add new ones only for roles that don't already map,
see Phase 5), is_active, created_at/updated_at.

**Seed data**: `backend/scripts/seed_supplier_types.py` (new, follow `seed_approver_matrix.py`'s
upsert-by-code pattern so it's safe to re-run) — the four supplier types from FS Section 17
verbatim: `STD_VENDOR` (AUTO), `CONSULTANT` (MANUAL), `ONE_TIME_VENDOR` (NONE),
`HIGH_RISK_VENDOR` (MANUAL).

**Backend**: admin CRUD (`backend/app/crud/supplier_type.py`, `routers/supplier_type.py`,
admin-gated like the Template admin router) — list/get/create/update/deactivate. No delete;
mirror the draft/published/deprecated pattern only if supplier types genuinely need
versioning (FS doesn't ask for it — don't add it speculatively).

**Frontend**: `frontend/app/dashboard/admin/supplier-types/page.tsx` — table + edit form,
same visual pattern as `admin/templates`. `SupplierType` picker becomes a required field
wherever a Supplier Request is created (Phase 2).

**Tests**: seed script is idempotent (run twice, assert no duplicate rows); CRUD round-trip.

---

## Phase 2 — Supplier creation + registration trigger (the missing link)

Goal: actually build FS Section 5.2 steps 5-6, which don't exist in any form today.

**On Supplier Request final approval** (find where `WorkflowInstance` completion is currently
handled for `entity_type="supplier_request"` — likely needs a completion hook next to the
pattern in `services/procurement_workflow.py`'s `auto_create_po_from_requisition`, which is
the closest existing analog: "on approval, auto-create the next document"):
1. Create a `Supplier` row from the approved `SupplierRequest`'s data (name, category, etc.)
   if one doesn't already exist for this request — check `Supplier` model fields, map what
   exists, leave the rest to be filled by registration.
2. Look up the `SupplierRequest`'s `SupplierType` (add `supplier_type_id` FK to
   `SupplierRequest` in Phase 2 if it isn't already on the model from Phase 1's frontend
   change) and branch on `registration_mode`:
   - **AUTO**: immediately generate and "send" (Phase 4's Excel engine) the registration
     workbook; start the SLA timer (Phase 6).
   - **MANUAL**: create a `WorkflowTask`-or-equivalent "Pending Registration" task assigned
     per FS Section 6, completable only by the Supplier Request Creator or an SLP Admin — completing
     it triggers the same Excel-send as AUTO.
   - **NONE**: mark the supplier active with no registration step; skip straight to FS
     Section 5.2 step 9 (Completed).
3. Audit-log every transition the same way `ProcurementAuditEvent` does for procurement
   documents — find or add an equivalent for supplier-side events, don't invent a third audit
   log table if one already exists for suppliers.

**Tests**: three integration tests, one per registration_mode, asserting the right thing
happens (Excel generated immediately / pending task created / supplier goes straight to
active) and nothing happens for the other two modes.

---

## Phase 3 — Questionnaire modules on Template Framework

Goal: FS Section 8's modules (Core, Tax, Bank, Compliance, ESG, InfoSec, Financial Stability)
as real `TemplateDefinition`s, reusing the engine rather than rebuilding it (see audit above
for the grade-band decision you need to make first).

- Add `supplier_registration` to `TEMPLATE_MODULES` (`models/template.py`) — or, if the FS's
  seven sub-modules genuinely need independent visibility/scoring/versioning from each other,
  model each as its own module (`supplier_registration_core`, `..._tax`, etc.) instead of one
  module with seven sections. Pick based on whether `SupplierType.required_questionnaire_
  modules` (Phase 1) needs to reference them independently — it does, per FS Section 4 — so
  the multi-module split is very likely correct; confirm by checking whether
  `get_effective_template()` assumes one active template per module (it does, per the earlier
  Fable prompt) before committing to the design.
- Seed each module's questions from FS Section 8's field list via a script mirroring
  `seed_supplier_types.py`'s pattern.
- `TemplateResponse.entity_type="supplier_registration"`, `entity_id=<SupplierRegistration.id>`
  — one response row per module per registration (or one row spanning all required modules;
  decide and document, since Phase 4's Excel import needs to know which shape it's writing
  into).

**Tests**: reuse the existing `evaluate_visibility`/`score_response` unit test patterns, new
fixtures for FS Section 8/9's specific examples (grade-band boundaries per your Phase-1
decision above).

---

## Phase 4 — Excel Template & Import Engine (net new)

Goal: FS Sections 13-16, the one genuinely new subsystem this FS requires.

**Add `openpyxl` to `backend/requirements.txt`.**

**Generator** (`backend/app/services/excel_registration.py`):
- `generate_registration_workbook(supplier_registration, template_version, questionnaire_
  modules) -> bytes` — builds the workbook per FS Section 13.1: Instructions sheet
  (versions, mandatory-field legend), Supplier Information sheet (editable fields per Section
  14's column map, `SupplierID`/`SupplierType`/`TemplateVersion` locked via openpyxl cell
  protection + explicit sheet protection), one sheet per questionnaire module (hidden
  `QuestionID`/`ModuleID` columns, `Response` editable, `AllowedValues` as a data-validation
  dropdown sourced from each question's options, `ScoreFormula` locked/hidden — don't expose
  the actual scoring weights in a visible cell, that's an integrity leak as much as a UX one).
- Compute and embed a hash signature (FS Section 15.1) over the structural elements (sheet
  names, column headers, locked-cell values) — a simple SHA-256 over a canonical JSON
  representation of "what should not change" is enough; store the expected hash alongside the
  `SupplierRegistration` row so the import step can compare against it, not recompute a fresh
  expectation from the current template (which could have moved on since the file was sent).

**Storage**: the generated workbook and the supplier's returned workbook both need to persist
somewhere real — resolve the "no object storage client wired anywhere" gap flagged in the
audit above (this same gap already exists for `ProcurementAttachment`; decide whether to fix
both at once or scope this to registration-only and leave the older gap for later, but say
which explicitly).

**Import engine** (same file or a sibling `excel_import.py`):
- `parse_and_validate_workbook(file_bytes, expected_registration) -> ImportResult` following
  FS Section 16.2's exact step order: structural validation (Section 15.1 — version match,
  no added/removed sheets/columns, hidden columns still hidden, locked cells unchanged, hash
  match) before any field validation, so a tampered file fails fast with a structural error
  rather than a confusing field-level one.
- Field validation (Section 15.2): mandatory-filled, dropdown-membership, email format,
  numeric fields, bank-field regex, ISO country code.
- On success: map `QuestionID → Response` into the Phase 3 `TemplateResponse` rows, call
  `score_response()` per module, aggregate into `SupplierRegistration`, determine
  qualification (Phase 1's `qualification_rule` condition tree, evaluated the same way
  `evaluate_visibility` evaluates its condition trees — reuse, don't reimplement), and flip
  the registration to active/qualified per FS Section 7 step 9.
- On failure: generate `ErrorReport.xlsx` (one row per validation failure: sheet, cell,
  rule violated, expected vs actual) and `ImportSummary.txt` per FS Section 15.4/16.5 — return
  both as downloadable artifacts from the import endpoint, don't just return a JSON error list
  the SLP Admin has to interpret manually.

**Backend endpoints**: `POST /suppliers/registrations/{id}/send` (SLP Admin/Creator-triggered
for MANUAL mode, per Phase 2), `GET /suppliers/registrations/{id}/workbook` (download),
`POST /suppliers/registrations/{id}/import` (multipart upload, admin-gated per FS Section 3's
role table — SLP Admin only), single vs bulk import per FS Section 16.1 (bulk = loop the
single-import path, don't build a separate bulk code path that could drift from it).

**Tests**: round-trip test (generate → don't touch → re-import → assert identical scores/
answers), tamper tests (edit a locked cell, remove a column, change TemplateVersion — each
should produce the specific structural-error category from FS Section 16.4, not a generic
failure), and the full FS Section 15.2 field-validation matrix (bad email, bad country code,
non-numeric in a numeric field, dropdown value not in the allowed list).

---

## Phase 5 — Ad-hoc tasks & notifications wiring

- Ad-hoc tasks: implement per the audit's `WorkflowTask`-reuse decision. Trigger conditions
  (FS Section 10) come from `SupplierType.ad_hoc_task_templates` (Phase 1) — evaluated at the
  same points Phase 2's registration-trigger logic runs (on request approval, on registration
  import, on qualification determination — match FS Section 10's task types to the lifecycle
  point that should create them; don't create every configured task type at every point).
- Notifications: extend whatever service already creates `Notification` rows (find it — check
  where workflow task creation currently fires a notification, likely near
  `crud/workflow.py`'s task-creation path) to cover FS Section 11's event list: request
  submitted, approved/rejected, supplier created, registration pending, Excel sent, SLA
  reminders (needs a scheduled job — check if one already exists, e.g. for workflow task
  escalation, and hook into it rather than building a second cron/scheduler), registration
  completed, qualification completed. Email + in-app per Section 11; Teams/Slack explicitly
  optional — skip unless there's already an integration point for it (there almost certainly
  isn't; don't build one speculatively).
- Add role codes to `APPROVER_ROLE_CODES` (`models/approval.py:26`) only for roles that
  genuinely don't map onto an existing one — check current codes (`MANAGER, MANAGER_MANAGER,
  DEPT_HEAD, CFO, FIN_CTRL, PROC_HEAD, AP_HEAD, AP_PROCESSOR`, plus whatever
  `CATEGORY_MGR/RISK_TEAM/COMPLIANCE` additions the earlier Preferred Supplier phase already
  made — check before re-adding) against FS Section 17's matrix (`BU_MANAGER`, `LEGAL`,
  `RISK`, `SLP_ADMIN` look like the genuinely new ones).

**Tests**: one integration test per Supplier Type's `ApprovalWorkflowConfig` chain (all four
from Section 17), asserting the right roles get tasks in the right order.

---

## Phase 6 — Frontend surfacing

- `frontend/app/dashboard/admin/supplier-types/page.tsx` (Phase 1).
- Supplier Request creation flow: Supplier Type picker becomes a required field (find the
  existing supplier-request form — per the earlier Fable prompt's audit this may still not
  exist as a real UI; if so, this phase is also where it finally gets built, using the
  existing `<DynamicTemplateForm>` component if that got built in the earlier batch, check
  first).
- Registration screen: SLP Admin view showing pending/sent/returned/imported status per
  registration, a "Send registration" button for MANUAL mode, "Download workbook" /
  "Upload completed workbook" actions, and the `ImportResult`/`ErrorReport` display
  (table of validation failures, download link for the generated `ErrorReport.xlsx`) when an
  import fails.
- Supplier detail page: registration status panel (mode, sent/returned dates, score, grade,
  qualification result) — find the existing supplier detail page pattern before adding a new
  section from scratch.
- Any new list table (registrations, ad-hoc tasks) uses the shared `Pagination` component
  (10 rows/page) — see Frontend conventions above.

**Tests**: `tsc --noEmit` and `next build` clean if you have build access; this sandbox
doesn't (confirmed 2026-08-01 — `@/lib` alias resolution fails, no npmjs.org access), so
manual review is the fallback if you're also running in a similarly restricted environment.

---

## Definition of done (all phases)

- The four Supplier Types from FS Section 17 exist as real configuration, not hardcoded
  if/else — changing a `SupplierType`'s `registration_mode` in the admin UI changes behavior
  on the next Supplier Request without a code change.
- Approving a `STD_VENDOR` Supplier Request creates a `Supplier`, generates a locked Excel
  workbook automatically, and starts an SLA timer — with zero manual steps.
- Approving a `CONSULTANT` Supplier Request creates a `Supplier` and a pending-registration
  task assigned to the Creator/SLP Admin; nothing is sent until someone completes that task.
- A tampered Excel (locked cell edited, or a column removed) is rejected at import with a
  structural error, not silently accepted or crashed on.
- A clean, correctly filled Excel import populates the questionnaire's `TemplateResponse`,
  computes a score/grade using the FS's actual band definitions (not the older 5-band scale,
  unless you deliberately decided to keep that and documented why), and determines
  qualification per the Supplier Type's `qualification_rule`.
- Ad-hoc tasks and notifications fire at the FS Section 10/11 trigger points using the
  existing `WorkflowTask`/`Notification` models — no parallel task or notification system was
  built.
- Every approval routing in FS Section 17's matrix goes through the existing workflow +
  approval-matrix engines — no new hand-rolled routing logic.
- State explicitly, in the final report back, which of the two candidate questionnaire
  foundations (Template Framework vs Metadata Engine) was used and why, and whether the
  grade-band mismatch was resolved by changing `score_response()` or by a deliberate
  module-specific override.
