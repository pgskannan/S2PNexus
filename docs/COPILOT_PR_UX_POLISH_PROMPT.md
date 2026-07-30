# Copilot Prompt — PR Form UX Polish + Search/Filters + Approver Picker

Written 2026-07-30. Five small, independent UX fixes. Reuse existing patterns in this
codebase rather than inventing new ones — each item below names the exact pattern to
copy. Keep this scoped; none of these need new architecture.

## 1. Category: predefined list instead of free text

Today `category` on requisitions/line items is a plain `<input>` with no lookup —
confirmed no category master-data table exists anywhere (only commodity-code tables:
`CommodityCode`, `CommodityAccountMapping`, `CommodityMatchingPolicy` in
`backend/app/models/commodity.py`).

**Fix:**
- Add a `Category` master-data table (id, code, name, is_active, tenant_id) — mirror
  the shape of the existing commodity/GL-account master data, not a new pattern.
- Add `GET /categories?search=` (and the admin CRUD endpoints), mirroring
  `backend/app/routers/commodity.py`'s existing pattern exactly.
- Add a `CategoryInput.tsx` component, copying `frontend/components/CommodityCodeInput.tsx`
  almost verbatim (debounced search, "Browse all" fallback, writes back a plain string
  code) — same UX as the commodity picker, just a different backend table.
- Replace every free-text Category `<input>` in
  `frontend/app/dashboard/requisitions/new/page.tsx` (header field ~line 375, line-item
  field ~line 524) with `<CategoryInput>`.
- Add a "Categories" card to `frontend/app/dashboard/admin/master-data/page.tsx`
  (`MasterDataCard`, same pattern as the existing commodity/GL-account cards) so admins
  can upload/manage the list via CSV, consistent with how commodity codes and GL
  accounts are already managed.
- Seed a small starter list (10-15 common categories) so the picker isn't empty on
  first use.

## 2. Placeholder text on PR form fields

`frontend/app/dashboard/requisitions/new/page.tsx`: Title (~line 261), Description
(~line 273), and Category currently have no `placeholder` prop at all — the native HTML
`placeholder` attribute already gives exactly the grey-text-disappears-on-typing
behavior wanted, it's just missing. Add `placeholder="..."` to these three plus any
other empty-by-default fields on this form and the requisition line-item rows
(commodity already has one via `CommodityCodeInput`'s `placeholder` prop — use it as
the reference). Suggested copy: Title → "e.g. Laptops for new engineering hires",
Description → "Business justification for this request", Category → "e.g. IT Hardware".

## 3. Tooltips on important fields

No tooltip component exists in the codebase — the only precedent is a native `title=`
attribute on one button (`CommodityCodeInput.tsx` line 104). Use that same
lightweight approach (native `title=` on the label or input) rather than building a
custom tooltip component — faster to ship and consistent with the one existing
precedent. Add to the PR form's most important/least self-explanatory fields: Supplier
("Who this requisition will be ordered from — required before it can convert to a PO"),
Category ("Classifies this line for spend reporting and GL mapping"), Estimated Value
("Used to determine whether this requisition requires approval"), Delay Until
("PO creation will be held until this date even after approval"), Priority
("High/Urgent priority may trigger different approval routing").

## 4. PR list: search, filters, export

`frontend/app/dashboard/requisitions/page.tsx` today has only a free-text search box.
Backend `list_requisitions`/`get_requisitions`
(`backend/app/routers/procurement.py`, `backend/app/crud/procurement.py`) only support
`search` and `status` as query params.

**Backend:** add `category`, `supplier_id`, `created_after`, `created_before` query
params to `list_requisitions` and thread them through `get_requisitions`/
`get_requisitions_count` — same style as the existing `status` filter (a `.where(...)`
appended conditionally).

**Frontend:** add a filter bar to the requisitions list page, copying the status
`<select>` pattern already working on `frontend/app/dashboard/purchase-orders/page.tsx`
(lines ~64-83) — add one for status (values already known from the requisition
lifecycle), one for category (use the new `CategoryInput` picker from item 1), a
supplier `<select>` (reuse `listSuppliers()`, same as the PR creation form), and two
date inputs for created-after/before.

**Export:** no export pattern exists anywhere in the app yet — build the simplest
version: a client-side "Export CSV" button that takes the currently-loaded/filtered
rows (already fetched via `listRequisitions`) and generates a CSV in-browser
(e.g. build the CSV string and trigger a `Blob` download) — no new backend endpoint
needed for this scope. If the filtered result set can exceed the default page size,
re-fetch with a higher `limit` (existing endpoints already support up to 1000) before
exporting rather than only exporting the visible page.

## 5. Workflow designer: approver/recipient picker instead of raw UUIDs

`frontend/components/WorkflowNodeInspector.tsx`: the Approvers field (~line 67-80,
labeled "Approvers (comma separated UUIDs)"), Recipients (~line 116-129), and
Escalate To (~line 102-109) all require typing raw UUIDs today — the canvas and
Approval-node mechanics themselves already work fine, this is purely an input-UX gap.

**Fix:** build a `UserPicker.tsx` component — debounced search against the existing
admin `GET /users?search=` endpoint (`backend/app/routers/users.py`, already built for
the admin Users page, requires superuser — consistent with workflow definitions being
an admin-configured area per spec 2.3.1), same debounce/dropdown UX as
`CommodityCodeInput`. For Approvers/Recipients (multi-select), show picked users as
removable chips backed by their UUIDs under the hood. For Escalate To (single), a
plain select-one variant. Swap all three fields in `WorkflowNodeInspector.tsx` to use
it instead of the raw comma-separated text inputs.

## Non-goals

Don't build a generic reusable Tooltip component library, a generic reusable
export-to-CSV backend service, or expand category/master-data beyond requisitions
(commodity codes already cover PO/invoice categorization elsewhere) — keep each fix
scoped to what's asked above.

## Definition of done

- Category is a searchable dropdown backed by a real (admin-manageable) list, on both
  the requisition header and line items.
- Title/Description/Category show grey placeholder text that behaves natively.
- Hovering Supplier, Category, Estimated Value, Delay Until, and Priority shows a
  tooltip.
- Requisitions list page supports filtering by status, category, supplier, and a
  created-date range, plus a working CSV export of the current filtered results.
- Workflow designer's Approvers/Recipients/Escalate-to fields use a searchable people
  picker, not raw UUID text entry.
- `tsc --noEmit` and `next build` clean; existing requisition/workflow tests unaffected.
