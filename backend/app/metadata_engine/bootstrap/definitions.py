"""Default metadata bootstrap definitions for platform business objects."""

from app.metadata_engine.bootstrap.registry import (
    MetadataLayoutDefinition,
    MetadataObjectDefinition,
    register_metadata_layout,
    register_metadata_object,
)


# Metadata object definitions
register_metadata_object(
    MetadataObjectDefinition(
        name="supplier_request",
        display_name="Supplier Request Metadata",
        description="Metadata registry for supplier request documents and workflow.",
        entity_type="supplier_request",
        searchable=True,
        auditable=True,
        supports_workflow=True,
        supports_approval=True,
        supports_attachments=True,
        supports_comments=True,
        supports_forms=True,
        classification=["supplier", "procurement"],
    )
)

register_metadata_object(
    MetadataObjectDefinition(
        name="supplier_registration",
        display_name="Supplier Registration Metadata",
        description="Metadata registry for supplier registration onboarding.",
        entity_type="supplier_registration",
        searchable=True,
        auditable=True,
        supports_workflow=True,
        supports_approval=True,
        supports_attachments=False,
        supports_comments=True,
        supports_forms=True,
        classification=["supplier", "compliance"],
    )
)

register_metadata_object(
    MetadataObjectDefinition(
        name="procurement_requisition",
        display_name="Procurement Requisition Metadata",
        description="Metadata registry for procurement requisitions.",
        entity_type="procurement_requisition",
        searchable=True,
        auditable=True,
        supports_workflow=True,
        supports_approval=True,
        supports_attachments=True,
        supports_comments=True,
        supports_forms=True,
        classification=["procurement"],
    )
)

register_metadata_object(
    MetadataObjectDefinition(
        name="purchase_order",
        display_name="Purchase Order Metadata",
        description="Metadata registry for purchase orders.",
        entity_type="purchase_order",
        searchable=True,
        auditable=True,
        supports_workflow=False,
        supports_approval=False,
        supports_attachments=True,
        supports_comments=True,
        supports_forms=False,
        classification=["procurement"],
    )
)


# Metadata layout definitions
register_metadata_layout(
    MetadataLayoutDefinition(
        metadata_object_name="supplier_request",
        version=1,
        schema={
            "type": "object",
            "properties": {
                "requestor_id": {"type": "string", "format": "uuid"},
                "title": {"type": "string"},
                "business_justification": {"type": ["string", "null"]},
                "commodity_categories": {"type": ["string", "null"]},
                "suggested_supplier_name": {"type": ["string", "null"]},
                "existing_supplier_check": {"type": "boolean"},
                "preferred_region": {"type": ["string", "null"]},
                "estimated_annual_spend": {"type": ["number", "null"]},
                "diversity_required": {"type": "boolean"},
            },
            "required": ["requestor_id", "title"],
        },
    )
)

register_metadata_layout(
    MetadataLayoutDefinition(
        metadata_object_name="supplier_registration",
        version=1,
        schema={
            "type": "object",
            "properties": {
                "submitted_by": {"type": "string", "format": "uuid"},
                "company_name": {"type": "string"},
                "company_address": {"type": ["string", "null"]},
                "tax_id": {"type": ["string", "null"]},
                "contact_person": {"type": ["string", "null"]},
                "business_category": {"type": ["string", "null"]},
                "compliance_documents": {"type": ["array", "null"], "items": {"type": "string"}},
            },
            "required": ["submitted_by", "company_name"],
        },
    )
)

register_metadata_layout(
    MetadataLayoutDefinition(
        metadata_object_name="procurement_requisition",
        version=1,
        schema={
            "type": "object",
            "properties": {
                "requested_by": {"type": "string", "format": "uuid"},
                "requisition_number": {"type": "string"},
                "category": {"type": ["string", "null"]},
                "currency": {"type": ["string", "null"]},
                "total_amount": {"type": ["number", "null"]},
                "due_date": {"type": ["string", "null"], "format": "date"},
            },
            "required": ["requested_by", "requisition_number"],
        },
    )
)

register_metadata_layout(
    MetadataLayoutDefinition(
        metadata_object_name="purchase_order",
        version=1,
        schema={
            "type": "object",
            "properties": {
                "purchase_order_number": {"type": "string"},
                "supplier_id": {"type": "string", "format": "uuid"},
                "order_total": {"type": ["number", "null"]},
                "currency": {"type": ["string", "null"]},
            },
            "required": ["purchase_order_number", "supplier_id"],
        },
    )
)
