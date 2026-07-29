# Prompt: Unified Admin Control Plane (Ariba-style)

Copy each phase below into Copilot **one at a time, in order**. Phase 0 has no dependencies. Phase 1 depends on Phase 0's shell existing. Phase 2 depends on Phase 0. Do not start the "Phase 3 (parked)" backend work without explicit sign-off — see that section for why.

Paste the "Context for every phase" block once at the start of the session, then paste one phase's prompt.

---

## Context for every phase (paste once)

You are extending S2PNexus, a Next.js (App Router) + FastAPI/SQLAlchemy async/Pydantic v2 codebase, to build a single consolidated Admin section modeled on SAP Ariba's administrative scope. Today admin functionality is scattered: a single `/dashboard/settings` page holds AI provider selection, document numbering, and three master-data upload cards, gated by `user.role === "administrator"`. Everything else administrative either has no UI at all (even though the backend API exists) or has no backend at all. Follow these conventions exactly:

**Frontend**
1. Pages live under `frontend/app/dashboard/...`, wrapped automatically by `frontend/app/dashboard/layout.tsx` (`AuthGuard` + `Nav` sidebar + `TopBar`). No per-page auth boilerplate needed.
2. Client-side admin gating: `const isAdmin = user?.role === "administrator"` (see `frontend/app/dashboard/settings/page.tsx`). Non-admins should still be able to *view* read-only admin screens where the underlying API allows it (mirrors the existing Settings page's read-only mode for AI provider), and see a plain sentence explaining they can't edit — never just hide the whole page silently.
3. Reuse the existing card visual language: `<div className="card">` sections, `btn-primary` / `btn-secondary` / `input-field` / `label` utility classes already defined in the Tailwind config — don't invent new component styling.
4. Reuse `MasterDataCard` (defined in `settings/page.tsx`) for any new count/upload/download/deactivate-all master-data dataset instead of writing a new upload widget. If it needs to move to a shared location because multiple pages use it now, extract it to `frontend/components/MasterDataCard.tsx` with the same props shape and update the Settings page's import — don't fork it.
5. All API calls go through typed wrapper functions in `frontend/lib/api.ts` (axios instance with interceptors already configured there) — never call `fetch`/`axios` directly from a page component. Add new wrapper functions next to the existing ones, following the naming and error-handling pattern (`extractErrorMessage` for surfacing API errors).
6. Add new response/request shapes to `frontend/lib/types.ts` next to the existing ones (e.g. `User`, `DocumentNumberingFormat`).
7. `frontend/components/Nav.tsx` holds a flat `links` array rendered in a fixed sidebar — it's already at 12 items and visually full. Don't add more top-level entries for this work. Replace the existing `{ href: "/dashboard/settings", label: "Settings", icon: "settings" }` entry with `{ href: "/dashboard/admin", label: "Admin", icon: "settings" }` (reuse the existing settings icon unless you add a new SVG to `frontend/public/icons/`). Keep `/dashboard/settings` as a route that redirects to `/dashboard/admin/master-data` (`redirect()` in a server component or a `useEffect` + `router.replace`) so any existing bookmarks/tests don't 404.

**Backend**
8. Admin authorization in routers is inconsistent today — most new routers (`org_structure.py`, `address.py`, `budget.py`, `document_numbering.py`) use a local `_require_admin(current_user)` helper (`role != UserRole.ADMINISTRATOR and not is_superuser` → 403), while `users.py` uses a `Depends(get_current_active_superuser)` dependency instead. When adding endpoints to an existing router, match that file's existing pattern; don't mix the two styles within one file.
9. `UserRole` enum (`app/models/user.py`) has exactly these values: `administrator`, `procurement_manager`, `buyer`, `requester`, `supplier_manager`, `category_manager`, `ap_clerk`, `contract_manager`. There is no separate "sourcing manager" / "contract negotiator" / "spend analyst" role today — `category_manager` and `contract_manager` are the closest existing roles for the Sourcing admin domain; don't add new roles as part of this work without flagging it.
10. Tenant scoping, workflow-engine reuse, document-numbering reuse, and the single-Alembic-head rule all apply exactly as described in `docs/COPILOT_ENTERPRISE_PROCUREMENT_PROMPT.md`'s context block — don't repeat those mistakes (branching migration heads, bespoke approval tables instead of the Workflow engine, etc.).
11. Follow `docs/DOMAIN_DEVELOPMENT_STANDARD.md` for any *new* domain (model → schema → crud → router → migration → tests). Phases 0–2 below deliberately avoid needing this — they only touch existing domains. Phase 3 (parked) would need it.

**Current inventory — what's real vs. not, mapped to the four admin domains.** Treat this table as ground truth; don't assume something exists just because it's a reasonable feature to have.

| Domain | Activity | Status | Notes |
|---|---|---|---|
| Core P2P | User & Access Management | **API exists, no UI** | `app/routers/users.py`: list/get/patch/delete, admin-only. No frontend page at all today. |
| Core P2P | Custom group assignments | **Nothing** | No group model. Placeholder only. |
| Core P2P | Delegated approvals | **Nothing** | Workflow engine assigns tasks to a user/role, but has no "forward my approvals to X while I'm out" concept. Placeholder only. |
| Core P2P | Active approval queues | **Exists, has its own UI already** | `/dashboard/workflow/instances` + `GET /workflow/tasks/my`. Don't rebuild — link to it. |
| Core P2P | Catalog Management | **Nothing** | No catalog/item/supplier-catalog model anywhere in `app/models/`. Placeholder only. |
| Core P2P | Approval routing lookup tables | **Exists, has its own UI already** | `/dashboard/workflow/definitions`. Link to it. |
| Core P2P | Custom enumerations | **Nothing** | Placeholder only. |
| Core P2P | Tax calculation matrices | **Nothing** | `ProcurementInvoiceLineItem`/line items have a free-text `tax_code`, no matrix/rate table. Placeholder only. |
| Core P2P | Budget rules | **API exists, no UI** | `app/routers/budget.py`: full CRUD + `/budgets/check`, admin-gated. No frontend page. |
| Core P2P | P-Card controls | **Nothing** | Placeholder only. |
| Core P2P | Site configuration / feature flags | **Nothing** | Only the AI-provider setting exists as a "platform toggle." Placeholder only. |
| Core P2P | User sessions | **Nothing** | Auth is stateless JWT; no session table. Placeholder only. |
| Core P2P | Audit logs | **Partial, buried** | `ProcurementAuditEvent` (`app/models/procurement.py`) records requisition-level events only, with no admin-facing list endpoint. Not a system-wide audit log. Placeholder for this pass; note the model as prior art if built later. |
| Core P2P | Master data import/export | **API exists, no unified UI** | Commodity codes / GL accounts / mapping (count+upload+download+delete) already wired in Settings. Departments/cost centers/plants (`org_structure.py`) have count+upload+delete but **no download/export endpoint yet**. |
| Sourcing/Contracts | RFx/auction templates | **Nothing** | `sourcing.py` is transactional (create/list events), not a template library. Placeholder only. |
| Sourcing/Contracts | Contract clause library | **Nothing** | Placeholder only. |
| Sourcing/Contracts | Standardized workflow conditions | **Exists, has its own UI already** | Same Workflow Definitions screen as above — one condition engine, reused everywhere. Link to it. |
| Sourcing/Contracts | Sourcing/contract permission scope | **Partially covered by Users screen** | `category_manager`/`contract_manager` roles are assignable via the new Users screen (Phase 1). No finer-grained scope than role today. |
| Sourcing/Contracts | Custom fields / scoring rules for RFx | **Nothing** | Placeholder only. |
| Sourcing/Contracts | Sync awarded events/contracts → PO/catalog | **Nothing automatic** | Requisition→PO conversion exists but nothing syncs sourcing/contract awards into it. Placeholder only. |
| Supplier Mgmt | Onboarding & mass actions | **Nothing** | `supplier_registration.py` handles one registration at a time; no batch invite/import endpoint. Placeholder only. |
| Supplier Mgmt | Questionnaire engine | **Nothing** | Registration captures responses to a fixed shape, not a template builder. Placeholder only. |
| Supplier Mgmt | Lifecycle & status rules | **Exists, has its own UI already** | Supplier Lifecycle Phase 1 shipped 2026-07-27 — lifecycle transitions live on `/dashboard/suppliers`. Link to it. |
| Supplier Mgmt | Project/template version control | **Nothing** | Placeholder only. |
| Supplier Mgmt | ERP integration sync | **Nothing** | Placeholder only. |
| Supplier Mgmt | Supplier analytics/reporting export | **Partial** | Spend rollups exist (`getSupplierSpendRollup`, `/dashboard/spend`) but no onboarding-cycle-time/risk export. Placeholder, note spend page as nearest prior art. |
| Platform/Data | Data import/export engine | **API exists, no unified UI** | This *is* the master-data upload pattern above — consolidate into one page instead of building something new. |
| Platform/Data | System integration hub (webhooks/API/ERP connectors) | **Nothing** | Placeholder only. |
| Platform/Data | Definition control (schema/mapping/transform rules) | **Nothing** | Placeholder only. |

---

## Phase 0 — Admin shell with a placeholder screen for every activity above

Goal: one consolidated `/dashboard/admin` section that lists *everything* in the inventory table, so nothing SAP-Ariba-shaped is missing from the map — even the pieces with no backend yet. Frontend-only, no backend changes.

**Routes** (`frontend/app/dashboard/admin/...`, one `page.tsx` per row unless noted):
- `admin/layout.tsx`: renders a horizontal or left-rail sub-nav with four tabs — `Core P2P`, `Sourcing & Contracts`, `Supplier Management`, `Platform & Data` — matching the four domains above, wrapping `{children}`.
- `admin/page.tsx`: redirects to `admin/core-p2p` (first tab), same pattern as any other index redirect in the app.
- `admin/core-p2p/page.tsx`, `admin/sourcing/page.tsx`, `admin/suppliers/page.tsx`, `admin/platform-data/page.tsx`: each renders a grid of cards, one per activity row in that domain from the inventory table above. Every card shows: title, one-line description (lifted from the table), and a status pill — `Live` (green) if it links to a real working screen, `Coming soon` (slate) if it's backend-less. `Live` cards are `<Link>`s to the real route (existing or built in Phase 1/2 below); `Coming soon` cards render inline (not a link) with the description and nothing else — no fake buttons that do nothing.
- Build one shared `frontend/components/AdminActivityCard.tsx` for this grid — don't hand-roll the card markup four times.

**Migrate, don't duplicate**: `admin/master-data/page.tsx` becomes the new home for the three existing `MasterDataCard`s (commodity codes, GL accounts, mapping) plus the AI provider card and document numbering card, moved out of `settings/page.tsx` verbatim (same components, same `lib/api.ts` calls). Delete `frontend/app/dashboard/settings/page.tsx`'s content and replace it with the redirect described in the Context block's point 7. The "Master data import/export" card in `admin/platform-data` links to this same `admin/master-data` page rather than being a separate implementation.

**Nav change**: apply Context block point 7 (swap the `Settings` link for `Admin`).

No tests needed for Phase 0 beyond a manual click-through (this is presentational scaffolding), but do add one Playwright/RTL smoke test if the repo already has a frontend test harness — check `frontend/package.json` for an existing test script before deciding whether to add one from scratch.

---

## Phase 1 — Wire the Core P2P admin screens that already have a working API

Each of these replaces a "Coming soon" card from Phase 0 with a real `Live` one. Do these five in any order; they don't depend on each other.

### 1.1 User & Access Management (`admin/users/page.tsx`)
New page, new `lib/api.ts` functions: `listUsers({skip, limit, search, sort_by, sort_order})` → `GET /users`, `getUser(id)` → `GET /users/{id}`, `updateUser(id, payload)` → `PATCH /users/{id}` (payload: `email?`, `full_name?`, `role?`, `is_active?`, `is_superuser?`), `deleteUser(id)` → `DELETE /users/{id}`. Add a `UserListResponse`/`UserUpdate` pair to `types.ts` matching `app/schemas/user.py`.

Screen: paginated/searchable table (email, full name, role, active, superuser), a row-click or "Edit" action opening an inline or modal form to change role (`<select>` over the 8 `UserRole` values from Context point 9), toggle `is_active`/`is_superuser`, and a delete action with a confirm dialog that also surfaces the backend's "cannot delete yourself" 400 cleanly via `extractErrorMessage`. Read-only for non-admins (list/view only, no edit/delete controls rendered) — the backend already 403s non-admins on write, but don't rely on the API error alone; hide the controls too.

### 1.2 Master Data hub — extend with org structure (`admin/master-data/page.tsx`, extends Phase 0's migrated page)
Add three more `MasterDataCard`s for Departments, Cost Centers, Plants, wired to the existing `org_structure.py` endpoints (`/departments/master-data/{count,upload}` + `DELETE /departments/master-data`, and the equivalent `cost-centers`/`plants` paths). These three don't have a download/export endpoint yet — add one to `org_structure.py` per dataset, mirroring `gl_accounts.py`'s existing `GET /gl-accounts/export` (same CSV-streaming shape, same admin gate). Add the matching CRUD read-all function next to the existing `count_departments`/`count_cost_centers`/`count_plants` in `app/crud/org_structure.py`, then the corresponding `lib/api.ts` wrappers (`downloadDepartments`, etc.) so `MasterDataCard`'s optional `download` prop is populated the same way `downloadCommodityCodes`/`downloadGlAccounts` already are.

### 1.3 Budget Rules (`admin/budgets/page.tsx`)
New page, new `lib/api.ts` functions: `listBudgets({fiscal_year?})` → `GET /budgets`, `createBudget(payload)` → `POST /budgets`, `getBudget(id)` → `GET /budgets/{id}`, `updateBudget(id, payload)` → `PUT /budgets/{id}`, `checkBudget({requested_amount, gl_account_code?, cost_center?, fiscal_year?, fiscal_period?})` → `GET /budgets/check`. Add `Budget`/`BudgetCreate`/`BudgetUpdate`/`BudgetCheckResponse` types matching `app/schemas/budget.py`.

Screen: table of budgets by fiscal year/scope (`gl_account` | `cost_center` | `department`) with a create/edit form (`budgeted_amount`, `enforcement`: `hard`/`soft`/`none`), plus a small "check availability" panel that calls `/budgets/check` and shows committed/actual/available live — this doubles as a way to sanity-check the numbers this same API drives on the PO-approval budget gate (see the split-accounting/budget Phase 5 memory), so surfacing it here has real diagnostic value beyond CRUD.

### 1.4 Shared Address Book (`admin/addresses/page.tsx`)
The read side exists (`GET /addresses/shared`) but there's no admin write endpoint for tenant-shared addresses, even though the CRUD functions already support it. In `app/routers/address.py`, add three endpoints reusing the file's existing `_require_admin` helper and the already-imported `create_address`/`update_address`/`delete_address` CRUD functions (just call them with `owner_type="tenant"`, `owner_id=None`, matching how `create_mine` calls them with `owner_type="user"` today):
- `POST /addresses/shared` (admin-only)
- `PATCH /addresses/shared/{address_id}` (admin-only)
- `DELETE /addresses/shared/{address_id}` (admin-only)

Then build the frontend page: list of shared addresses with create/edit/delete, admin-gated the same way as the other admin screens, read-only list for non-admins. Add `lib/api.ts` wrappers and extend `types.ts`'s address types if needed.

### 1.5 Link-out cards, no new build
Wire the `Live` status + real `<Link>` on the Phase-0 placeholder cards for: Active Approval Queues → `/dashboard/workflow/instances`, Approval Routing Lookup Tables → `/dashboard/workflow/definitions`, Standardized Workflow Conditions → `/dashboard/workflow/definitions`, Supplier Lifecycle & Status Rules → `/dashboard/suppliers`. These were already `Coming soon` placeholders in Phase 0 that actually have a home — just repoint them, don't build anything new.

**Tests**: for the two backend additions (1.2's export endpoints, 1.4's shared-address write endpoints), add real-DB integration tests following the existing pattern in `tests/integration/` (plain `def test_x(): asyncio.run(...)`, not `pytest-asyncio` fixtures) — at minimum: export returns the currently-loaded rows in the same shape as upload expects (round-trip), and a non-admin gets 403 on the three new address-write endpoints while an admin succeeds.

---

## Phase 2 — Supplier Management admin surfaces

Smaller than Phase 1 since most of this domain has no backend (per the inventory table, left as `Coming soon` from Phase 0). The one thing to wire:

Confirm `admin/suppliers/page.tsx`'s "Lifecycle & Status Rules" card links correctly to the existing supplier lifecycle transition UI on `/dashboard/suppliers/[id]` (built in the Supplier Lifecycle Phase 1 work) — if that screen doesn't already expose an admin-oriented view (e.g., a filtered list of suppliers by lifecycle status, or a bulk view of who's pending requalification/offboarding), consider whether a thin `admin/suppliers/lifecycle/page.tsx` list view is worth adding here, reusing `listSuppliers()` with a lifecycle-status filter if the API already supports one — check `app/routers/suppliers.py` for a `lifecycle_status` query param before assuming you need to add one.

Everything else in the Supplier Management domain (onboarding mass actions, questionnaire engine, project/template control, ERP sync, analytics export) stays exactly as Phase 0 left it — `Coming soon`, no backend work.

---

## Phase 3 (parked — do not start without explicit sign-off)

The remaining "Coming soon" cards (catalog management, custom enumerations, tax matrices, P-Card controls, site config/feature flags, user sessions, system-wide audit log, RFx/clause template libraries, sourcing custom fields/scoring, sourcing→catalog sync, supplier onboarding mass actions/questionnaire engine/ERP sync, and the platform integration hub/schema-mapping control) are all genuinely new domains — each would need the full model → schema → crud → router → migration → tests treatment from `docs/DOMAIN_DEVELOPMENT_STANDARD.md`, not a quick add. Current project priority is deploying P2P and revenue/customer-facing work, not new backend surface area, so leave these as honest placeholders until someone explicitly prioritizes one. If/when that happens, pull the relevant row out of this file and write it up with the same level of model/CRUD/router detail as `docs/COPILOT_ENTERPRISE_PROCUREMENT_PROMPT.md`'s phases — don't vibe-code a data model straight into a router.

---

## Definition of done (Phases 0–2)

- Every row in the inventory table above has a visible card somewhere under `/dashboard/admin`, correctly labeled `Live` or `Coming soon` — nothing from the user's original Ariba-style list is silently missing.
- `/dashboard/settings` still works (redirects, doesn't 404).
- Non-admins can view but not edit anywhere the API allows read access; write controls are hidden, not just server-rejected.
- The two small backend additions (org-structure export endpoints, shared-address write endpoints) have real-DB tests and follow the existing admin-gating pattern already in each file.
- Run the existing frontend build (`npm run build`) and the backend's existing test suite before calling any phase done — per the known pre-existing test gaps memory, don't chase failures unrelated to this change, but do make sure nothing you touched regressed.
