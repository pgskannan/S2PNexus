"""Registry of condition-step fields available per workflow entity_type, used
by the workflow designer's Field autocomplete (Node inspector, "Field" input
on a condition step).

Every `path` here is the EXACT key used in that entity type's
WorkflowInstanceStart.context dict (see the corresponding
services/*_workflow.py start_*_workflow function) -- crud/workflow.py's
_evaluate_condition does a flat `context.get(step["field"])` lookup, so
picking one of these paths in the designer is guaranteed to resolve at
runtime. No nested/dotted-path traversal or line-item (array) fields yet --
see the module docstring note at the bottom for what that would take.
"""

from __future__ import annotations

from typing import TypedDict


class FieldSpec(TypedDict):
    path: str
    label: str
    type: str  # "number" | "string" | "boolean" | "date"


WORKFLOW_FIELD_REGISTRY: dict[str, list[FieldSpec]] = {
    "requisition": [
        # Pre-existing context keys (services/procurement_workflow.py start_requisition_approval_workflow)
        {"path": "estimated_value", "label": "Estimated value", "type": "number"},
        {"path": "priority", "label": "Priority", "type": "string"},
        {"path": "category", "label": "Category", "type": "string"},
        {"path": "requested_by", "label": "Requested by (user ID)", "type": "string"},
        {"path": "requisition_id", "label": "Requisition ID", "type": "string"},
        # Added alongside this registry -- see the same function for the new keys
        {"path": "account_code", "label": "Account code", "type": "string"},
        {"path": "commodity", "label": "Commodity", "type": "string"},
        {"path": "supplier_id", "label": "Supplier ID", "type": "string"},
        {"path": "currency", "label": "Currency", "type": "string"},
        {"path": "need_by_date", "label": "Need-by date", "type": "date"},
        {"path": "is_emergency", "label": "Emergency buy", "type": "boolean"},
        {"path": "header_tax", "label": "Header tax", "type": "number"},
        {"path": "shipping_cost", "label": "Shipping cost", "type": "number"},
    ],
    "purchase_order": [
        # Pre-existing context keys (services/procurement_workflow.py start_purchase_order_approval_workflow)
        {"path": "total_amount", "label": "Total amount", "type": "number"},
        {"path": "supplier_id", "label": "Supplier ID", "type": "string"},
        {"path": "purchase_order_id", "label": "Purchase order ID", "type": "string"},
        {"path": "lifecycle_status", "label": "Lifecycle status", "type": "string"},
        # Added alongside this registry -- see the same function for the new keys
        {"path": "order_number", "label": "Order number", "type": "string"},
        {"path": "status", "label": "Status", "type": "string"},
        {"path": "subtotal", "label": "Subtotal", "type": "number"},
        {"path": "tax_total", "label": "Tax total", "type": "number"},
        {"path": "shipping_amount", "label": "Shipping amount", "type": "number"},
        {"path": "grand_total", "label": "Grand total", "type": "number"},
        {"path": "currency", "label": "Currency", "type": "string"},
        {"path": "incoterms", "label": "Incoterms", "type": "string"},
        {"path": "payment_terms", "label": "Payment terms", "type": "string"},
    ],
    "contract": [
        {"path": "amount", "label": "Amount", "type": "number"},
        {"path": "value", "label": "Value", "type": "number"},
        {"path": "contract_type", "label": "Contract type", "type": "string"},
        {"path": "supplier_id", "label": "Supplier ID", "type": "string"},
        {"path": "lifecycle_status", "label": "Lifecycle status", "type": "string"},
        {"path": "contract_id", "label": "Contract ID", "type": "string"},
    ],
    "sourcing_event": [
        {"path": "amount", "label": "Amount", "type": "number"},
        {"path": "estimated_value", "label": "Estimated value", "type": "number"},
        {"path": "event_type", "label": "Event type", "type": "string"},
        {"path": "category", "label": "Category", "type": "string"},
        {"path": "lifecycle_status", "label": "Lifecycle status", "type": "string"},
        {"path": "sourcing_event_id", "label": "Sourcing event ID", "type": "string"},
    ],
    "goods_receipt": [
        {"path": "receipt_id", "label": "Receipt ID", "type": "string"},
        {"path": "receipt_number", "label": "Receipt number", "type": "string"},
        {"path": "purchase_order_id", "label": "Purchase order ID", "type": "string"},
        {"path": "has_exceptions", "label": "Has exceptions", "type": "boolean"},
        {"path": "status", "label": "Status", "type": "string"},
        {"path": "inspection_status", "label": "Inspection status", "type": "string"},
    ],
    "invoice_approval": [
        {"path": "invoice_id", "label": "Invoice ID", "type": "string"},
        {"path": "amount", "label": "Amount", "type": "number"},
        {"path": "supplier_id", "label": "Supplier ID", "type": "string"},
        {"path": "block_status", "label": "Block status", "type": "string"},
        {"path": "match_status", "label": "Match status", "type": "string"},
    ],
    "invoice_exception": [
        {"path": "exception_id", "label": "Exception ID", "type": "string"},
        {"path": "invoice_id", "label": "Invoice ID", "type": "string"},
        {"path": "exception_type", "label": "Exception type", "type": "string"},
        {"path": "variance_amount", "label": "Variance amount", "type": "number"},
        {"path": "resolution_status", "label": "Resolution status", "type": "string"},
    ],
    "supplier": [
        {"path": "supplier_id", "label": "Supplier ID", "type": "string"},
        {"path": "name", "label": "Name", "type": "string"},
        {"path": "lifecycle_status", "label": "Lifecycle status", "type": "string"},
        {"path": "reason", "label": "Reason", "type": "string"},
    ],
}


def get_fields_for_entity_type(entity_type: str) -> list[FieldSpec]:
    return WORKFLOW_FIELD_REGISTRY.get(entity_type, [])


# NOTE on scope (2026-08-01): this registry only covers scalar, header-level
# fields that are already flat keys in each entity's context dict -- it does
# NOT cover line-item fields (e.g. a requisition line's commodity code) or
# cross-document fields (e.g. referencing a PO's total from an invoice
# condition). Line items would need (a) the relevant start_*_workflow
# function to add a "field_name": [values...] array to context, and (b)
# crud/workflow.py's _evaluate_condition to grow list-aware comparison
# semantics (e.g. "any line item matches" for eq/in, max-value comparison for
# gt/gte/lt/lte) since the engine currently only compares scalars. Deferred
# as a separate change rather than bundled in here.
