# Manual Test Script — Dynamic Approval Matrix (Phases 1-4)

Written 2026-08-01, for testing the deployed build against
`https://s2pnexus-frontend-120737021520.us-central1.run.app`. Each phase is a
self-contained section — test in order, since later phases assume earlier
ones' data exists (the seeded approver matrix, in particular).

**Before you start**: confirm `backend/scripts/seed_approver_matrix.py` has
actually been run against the deployed database (see step 0.2). If it hasn't,
Phase 1's live-resolution preview and Phase 2's matrix table will both be
empty, and you'll be debugging a non-issue.

---

## 0. Setup

**0.1 — Health check.** Visit
`https://s2pnexus-backend-120737021520.us-central1.run.app/health`. Expect
`{"status":"healthy", ..., "database":"connected"}`.

**0.2 — Confirm the seed ran.** Log in as an administrator, go to
`/dashboard/admin` → Core P2P tab → **Dynamic approval matrix** card (or
directly to `/dashboard/admin/approvals`). The Approver Matrix tab should list
8 rows: `manager@s2pnexus-demo.local` through
`ap_processor@s2pnexus-demo.local`. If the table is empty, run the seed
script first (`cd backend && python -m scripts.seed_approver_matrix` wherever
`DATABASE_URL` points at the deployed DB) and come back to this step.

**0.3 — Log out/back in if this is your first login since the deploy.** A
code change touched auth-adjacent paths in prior work; if anything 401s
unexpectedly, this is the first thing to try.

---

## 1. Phase 1 — Dynamic approval-node UI

Location: `/dashboard/workflow/definitions`.

**1.1 Role-based approver + live resolution.**
Open the requisition definition the seed script published ("Requisition
approval (role-based)"), or create a new test definition. Click the
"Manager approval" node (or add a new Approval node). In the inspector,
confirm you see two buttons: **Named users** / **By role**.
- Click **By role**, select `MANAGER`.
- *Expected*: a box appears below reading "Currently resolves to: Demo
  Manager (primary)". If it says "No active approver seed matches this
  role", re-check step 0.2.

**1.2 Amount changes the resolution set.**
With the role still set to `DEPT_HEAD`, type `1000000` into "Preview with
amount". *Expected*: the preview updates to show no match (Demo Department
Head's seeded ceiling is $50,000) or a warning box, since $1M exceeds the
seeded limit. Clear the field back to empty or a low number and confirm Demo
Department Head reappears.

**1.3 Auto node.**
Click "Add auto" in the canvas toolbar. *Expected*: a green node appears on
the canvas; selecting it shows a one-line explainer, no fields to configure.

**1.4 AI rule node.**
Click "Add ai". *Expected*: a teal node appears; selecting it shows
"Auto-approve below amount", "Supplier risk threshold", and a "Category
routing" section with an inline add-row (category → route-to). Add one pair
(e.g. `IT` → `risk_review`), confirm it appears as a removable row.

**1.5 Escalate-to by role.**
On an approval node, under "Escalate to", click **By role**, pick `PROC_HEAD`.
*Expected*: text appears — "Stored as the resolved user: Demo Procurement
Head (the engine escalates to a specific user, so the role is resolved now,
not at runtime)". This is the one place Phase 1 stores a resolved value
instead of a live role — expected, not a bug (flagged when this was built;
true runtime role-escalation needs a backend schema field that doesn't exist
yet).

---

## 2. Phase 2 — Admin Dynamic Approval Matrix

Location: `/dashboard/admin/approvals`.

**2.1 View the seeded ladder.** Already confirmed in step 0.2 — 8 rows,
correct roles, ceilings ascending from MANAGER ($5,000) to CFO (no ceiling).

**2.2 Add a new approver.** Fill the form: pick any real user via the picker,
role `MANAGER`, an amount limit, category scope `IT`. Submit. *Expected*: new
row appears in the table immediately.

**2.3 Edit an existing approver.** Click **Edit** on any row, change the
approval limit, save. *Expected*: table reflects the new limit without a
page reload.

**2.4 Deactivate + verify exclusion.** Click **Deactivate** on the row you
just added, confirm the dialog. *Expected*: row disappears from the default
view; check "Show inactive" and it reappears greyed out, marked Inactive.
Then go back to Phase 1's role-resolution preview (1.1) for that same role —
the deactivated approver should no longer appear in the resolved list.

**2.5 Non-admin read-only check.** Log in as (or switch to) a non-admin
account. Visit `/dashboard/admin/approvals`. *Expected*: you see the tables
and the sentence "You can view... but only administrators can edit them" —
no Edit/Deactivate buttons, no create form.

**2.6 SLA Targets tab.** Switch to the SLA Targets tab. Add a target:
document type `requisition`, role `MANAGER`, 1440 minutes, severity
`WARNING`. *Expected*: appears in the table. Breach rate will show `—`
until at least one task has actually been measured against it — that's
expected on a fresh target, not a bug.

---

## 3. Phase 3 — Definition editing + versioning

Location: `/dashboard/workflow/definitions`.

**3.1 Start an instance on the current version.** Before editing anything,
create a requisition (or use an existing one) that will route through the
role-based requisition definition, so you have an in-flight instance to
protect. Confirm it shows up under `/dashboard/workflow/instances`.

**3.2 Edit the definition.** Back on the definitions page, click **Edit** on
"Requisition approval (role-based)". Change something small (e.g. bump
"Escalate after hours" on the Manager step from 24 to 48). Save.
*Expected*: the button read "Save as new version" before you clicked it, and
a note above the form said editing publishes a new version.

**3.3 Version history.** *Expected*: the list now shows the definition
grouped under one heading with **2 versions** — "Current" (today's date) and
"Version 1" with an **Archived** pill. The archived row has no Edit button
(only Delete, if your backend allows it).

**3.4 In-flight instance is untouched.** Go back to the instance you started
in 3.1 (`/dashboard/workflow/instances/{id}`). *Expected*: it's completely
unaffected — same status, same step, same `definition_id` as before the
edit. It should NOT jump to the new 48-hour escalation window.

**3.5 New instance uses the new version.** Start a fresh requisition through
the same flow. *Expected*: its escalation window is now 48 hours (verify via
the task's due date, roughly now + 48h, not +24h).

---

## 4. Phase 4 — Contract + Sourcing wiring

**Known gap, read first**: the Contract and Sourcing detail pages
(`/dashboard/contracts/[id]`, `/dashboard/sourcing/[id]`) are read-only
today — there's no Submit/Publish button in the UI yet. Triggering the
transition that starts a workflow instance currently requires the API
directly. The steps below use `curl`; everything else (approving the
resulting task) uses the normal UI.

**4.1 Create a workflow definition for contracts.** Via
`/dashboard/workflow/definitions` (same UI as Phase 1), create a new
definition: name "Contract approval test", entity type `contract`, one
Approval step, By role → `DEPT_HEAD` (or Named users → yourself, whichever
you want to verify). Save as published/active.

**4.2 Create a contract.** Go to `/dashboard/contracts/new`, fill in the
required fields, save. Note the contract's `id` from the URL
(`/dashboard/contracts/{id}`).

**4.3 Get an auth token.**
```
curl -s -X POST https://s2pnexus-backend-120737021520.us-central1.run.app/api/v1/auth/login \
  -d "username=YOUR_EMAIL&password=YOUR_PASSWORD" \
  -H "Content-Type: application/x-www-form-urlencoded" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
```

**4.4 Trigger the submit transition.**
```
curl -s -X POST https://s2pnexus-backend-120737021520.us-central1.run.app/api/v1/contracts/CONTRACT_ID/transition \
  -H "Authorization: Bearer YOUR_TOKEN" -H "Content-Type: application/json" \
  -d '{"action": "submit"}'
```
*Expected*: 200 response with `"approval_status": "pending"`.

**4.5 Confirm the instance started.** Go to
`/dashboard/workflow/instances`, filter or scan for `entity_type: contract`.
*Expected*: a new instance, status `in_progress`, one pending task.

**4.6 Approve via the normal UI.** Go to your workflow task inbox
(dashboard home or `/dashboard/workflow`, "My tasks"). *Expected*: the
contract approval task appears there like any other pending task — approve
it. Recheck the instance: status should flip to `completed`.

**4.7 Repeat 4.1–4.6 for sourcing**, substituting: entity type
`sourcing_event`, create via `/dashboard/sourcing/new`, and the transition
call:
```
curl -s -X POST https://s2pnexus-backend-120737021520.us-central1.run.app/api/v1/sourcing/events/EVENT_ID/transition \
  -H "Authorization: Bearer YOUR_TOKEN" -H "Content-Type: application/json" \
  -d '{"action": "publish"}'
```

**4.8 Fallback check (regression guard).** Create a *second* contract, but
this time transition it with `action: submit` **without** having any active
`entity_type="contract"` definition (temporarily archive the one from 4.1
via the definitions page, or test this on a fresh entity type nobody has
configured, e.g. create a contract before doing 4.1). *Expected*: the
transition still succeeds normally (status still flips to pending), and
`GET /workflow/instances?entity_type=contract&entity_id=...` returns an
empty list — no error, no instance, exactly today's pre-Phase-4 behavior.

---

## 5. Things to expect, not report as bugs

- Escalate-to "By role" resolves once at save time, not live at runtime
  (1.5) — a known, documented limitation, not a defect.
- `POST /api/v1/approval/approvers` (the plain create endpoint under the
  hood) still has no admin gate — any logged-in user can hit it directly.
  This is a known open item awaiting your explicit sign-off, not something
  broken by this build.
- Contract/Sourcing have no Submit/Publish button in the UI yet (Section 4) —
  by design for this pass, curl is the intended workaround until that UI
  ships.
- A fresh SLA target shows `—` for breach rate until a task actually
  completes or breaches against it.

If something outside this list breaks, that's a real bug — worth flagging
back with the exact step number from this script.
