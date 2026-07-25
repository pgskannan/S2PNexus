"""Add procurement tables (requisitions, purchase orders, receipts, invoices) and supplier_requests

Revision ID: f0a1b2c3d4e5
Revises: 69f2a7d2e2c5
Create Date: 2026-07-22 12:00:00.000000

These tables backed the Procurement reference domain and the Supplier Request
workflow from the start, but were only ever created via
Base.metadata.create_all() in tests/dev -- no Alembic revision covered them,
so `alembic upgrade head` against a real database would never create them.
This revision closes that gap. It's inserted directly after the initial
migration (down_revision points to 69f2a7d2e2c5, not the current head) since
these tables logically predate every other domain-specific migration; the
next migration in the existing chain (a1b2c3d4e5f6) has been re-pointed to
depend on this one instead of the initial migration directly.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f0a1b2c3d4e5'
down_revision: Union[str, Sequence[str], None] = '69f2a7d2e2c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'procurement_requisitions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('request_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('lifecycle_status', sa.String(length=50), nullable=False),
        sa.Column('requested_by', sa.UUID(), nullable=False),
        sa.Column('supplier_id', sa.UUID(), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('estimated_value', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('approval_status', sa.String(length=50), nullable=False),
        sa.Column('priority', sa.String(length=20), nullable=False),
        sa.Column('commodity', sa.String(length=100), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('account_code', sa.String(length=100), nullable=True),
        sa.Column('need_by_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('tenant_id', sa.UUID(), nullable=True),
        sa.Column('search_text', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id'], name=op.f('fk_procurement_requisitions_requested_by_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], name=op.f('fk_procurement_requisitions_supplier_id_suppliers'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_procurement_requisitions')),
    )
    op.create_index(op.f('ix_procurement_requisitions_title'), 'procurement_requisitions', ['title'], unique=False)
    op.create_index(op.f('ix_procurement_requisitions_status'), 'procurement_requisitions', ['status'], unique=False)
    op.create_index(op.f('ix_procurement_requisitions_lifecycle_status'), 'procurement_requisitions', ['lifecycle_status'], unique=False)
    op.create_index(op.f('ix_procurement_requisitions_supplier_id'), 'procurement_requisitions', ['supplier_id'], unique=False)
    op.create_index(op.f('ix_procurement_requisitions_tenant_id'), 'procurement_requisitions', ['tenant_id'], unique=False)

    op.create_table(
        'procurement_requisition_line_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('requisition_id', sa.UUID(), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('unit_price', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('line_total', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('commodity', sa.String(length=100), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('account_code', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['requisition_id'], ['procurement_requisitions.id'], name=op.f('fk_procurement_requisition_line_items_requisition_id_procurement_requisitions'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_procurement_requisition_line_items')),
    )
    op.create_index(op.f('ix_procurement_requisition_line_items_requisition_id'), 'procurement_requisition_line_items', ['requisition_id'], unique=False)

    op.create_table(
        'procurement_comments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('requisition_id', sa.UUID(), nullable=False),
        sa.Column('author_id', sa.UUID(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['requisition_id'], ['procurement_requisitions.id'], name=op.f('fk_procurement_comments_requisition_id_procurement_requisitions'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], name=op.f('fk_procurement_comments_author_id_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_procurement_comments')),
    )
    op.create_index(op.f('ix_procurement_comments_requisition_id'), 'procurement_comments', ['requisition_id'], unique=False)

    op.create_table(
        'procurement_attachments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('requisition_id', sa.UUID(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=True),
        sa.Column('storage_key', sa.String(length=500), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['requisition_id'], ['procurement_requisitions.id'], name=op.f('fk_procurement_attachments_requisition_id_procurement_requisitions'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_procurement_attachments_created_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_procurement_attachments')),
    )
    op.create_index(op.f('ix_procurement_attachments_requisition_id'), 'procurement_attachments', ['requisition_id'], unique=False)

    op.create_table(
        'procurement_audit_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('requisition_id', sa.UUID(), nullable=False),
        sa.Column('actor_id', sa.UUID(), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['requisition_id'], ['procurement_requisitions.id'], name=op.f('fk_procurement_audit_events_requisition_id_procurement_requisitions'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_procurement_audit_events_actor_id_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_procurement_audit_events')),
    )
    op.create_index(op.f('ix_procurement_audit_events_requisition_id'), 'procurement_audit_events', ['requisition_id'], unique=False)
    op.create_index(op.f('ix_procurement_audit_events_action'), 'procurement_audit_events', ['action'], unique=False)

    op.create_table(
        'purchase_orders',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('requisition_id', sa.UUID(), nullable=False),
        sa.Column('supplier_id', sa.UUID(), nullable=True),
        sa.Column('order_number', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('amendment_status', sa.String(length=50), nullable=False),
        sa.Column('change_order_reference', sa.String(length=100), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['requisition_id'], ['procurement_requisitions.id'], name=op.f('fk_purchase_orders_requisition_id_procurement_requisitions'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], name=op.f('fk_purchase_orders_supplier_id_suppliers'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_purchase_orders_created_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_purchase_orders')),
    )
    op.create_index(op.f('ix_purchase_orders_requisition_id'), 'purchase_orders', ['requisition_id'], unique=False)
    op.create_index(op.f('ix_purchase_orders_supplier_id'), 'purchase_orders', ['supplier_id'], unique=False)
    op.create_index(op.f('ix_purchase_orders_order_number'), 'purchase_orders', ['order_number'], unique=False)
    op.create_index(op.f('ix_purchase_orders_status'), 'purchase_orders', ['status'], unique=False)

    op.create_table(
        'purchase_order_versions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('purchase_order_id', sa.UUID(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('change_type', sa.String(length=50), nullable=False),
        sa.Column('changes', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], name=op.f('fk_purchase_order_versions_purchase_order_id_purchase_orders'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_purchase_order_versions_created_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_purchase_order_versions')),
    )
    op.create_index(op.f('ix_purchase_order_versions_purchase_order_id'), 'purchase_order_versions', ['purchase_order_id'], unique=False)

    op.create_table(
        'goods_receipts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('purchase_order_id', sa.UUID(), nullable=False),
        sa.Column('receipt_number', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('receipt_type', sa.String(length=50), nullable=False),
        sa.Column('received_quantity', sa.Integer(), nullable=False),
        sa.Column('returned_quantity', sa.Integer(), nullable=False),
        sa.Column('tolerance_percent', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('tolerance_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], name=op.f('fk_goods_receipts_purchase_order_id_purchase_orders'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_goods_receipts_created_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_goods_receipts')),
    )
    op.create_index(op.f('ix_goods_receipts_purchase_order_id'), 'goods_receipts', ['purchase_order_id'], unique=False)
    op.create_index(op.f('ix_goods_receipts_receipt_number'), 'goods_receipts', ['receipt_number'], unique=False)
    op.create_index(op.f('ix_goods_receipts_status'), 'goods_receipts', ['status'], unique=False)

    op.create_table(
        'procurement_invoices',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('invoice_number', sa.String(length=100), nullable=False),
        sa.Column('supplier_id', sa.UUID(), nullable=True),
        sa.Column('purchase_order_id', sa.UUID(), nullable=True),
        sa.Column('goods_receipt_id', sa.UUID(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('tax_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('match_status', sa.String(length=50), nullable=False),
        sa.Column('match_type', sa.String(length=20), nullable=False),
        sa.Column('duplicate_status', sa.String(length=20), nullable=False),
        sa.Column('duplicate_reason', sa.String(length=255), nullable=True),
        sa.Column('memo_type', sa.String(length=20), nullable=True),
        sa.Column('reference_invoice_id', sa.UUID(), nullable=True),
        sa.Column('matching_tolerance_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('matching_tolerance_percent', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], name=op.f('fk_procurement_invoices_supplier_id_suppliers'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], name=op.f('fk_procurement_invoices_purchase_order_id_purchase_orders'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['goods_receipt_id'], ['goods_receipts.id'], name=op.f('fk_procurement_invoices_goods_receipt_id_goods_receipts'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_procurement_invoices_created_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_procurement_invoices')),
    )
    op.create_index(op.f('ix_procurement_invoices_invoice_number'), 'procurement_invoices', ['invoice_number'], unique=True)
    op.create_index(op.f('ix_procurement_invoices_supplier_id'), 'procurement_invoices', ['supplier_id'], unique=False)
    op.create_index(op.f('ix_procurement_invoices_purchase_order_id'), 'procurement_invoices', ['purchase_order_id'], unique=False)
    op.create_index(op.f('ix_procurement_invoices_goods_receipt_id'), 'procurement_invoices', ['goods_receipt_id'], unique=False)
    op.create_index(op.f('ix_procurement_invoices_status'), 'procurement_invoices', ['status'], unique=False)
    op.create_index(op.f('ix_procurement_invoices_match_status'), 'procurement_invoices', ['match_status'], unique=False)

    op.create_table(
        'supplier_requests',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('requestor_id', sa.UUID(), nullable=False),
        sa.Column('business_justification', sa.Text(), nullable=True),
        sa.Column('commodity_categories', sa.String(length=255), nullable=True),
        sa.Column('suggested_supplier_name', sa.String(length=255), nullable=True),
        sa.Column('existing_supplier_check', sa.Boolean(), nullable=False),
        sa.Column('preferred_region', sa.String(length=100), nullable=True),
        sa.Column('estimated_annual_spend', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('diversity_required', sa.Boolean(), nullable=False),
        sa.Column('risk_justification', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('lifecycle_status', sa.String(length=50), nullable=False),
        sa.Column('approval_status', sa.String(length=50), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['requestor_id'], ['users.id'], name=op.f('fk_supplier_requests_requestor_id_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_supplier_requests')),
    )
    op.create_index(op.f('ix_supplier_requests_title'), 'supplier_requests', ['title'], unique=False)
    op.create_index(op.f('ix_supplier_requests_status'), 'supplier_requests', ['status'], unique=False)
    op.create_index(op.f('ix_supplier_requests_lifecycle_status'), 'supplier_requests', ['lifecycle_status'], unique=False)
    op.create_index(op.f('ix_supplier_requests_tenant_id'), 'supplier_requests', ['tenant_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_supplier_requests_tenant_id'), table_name='supplier_requests')
    op.drop_index(op.f('ix_supplier_requests_lifecycle_status'), table_name='supplier_requests')
    op.drop_index(op.f('ix_supplier_requests_status'), table_name='supplier_requests')
    op.drop_index(op.f('ix_supplier_requests_title'), table_name='supplier_requests')
    op.drop_table('supplier_requests')

    op.drop_index(op.f('ix_procurement_invoices_match_status'), table_name='procurement_invoices')
    op.drop_index(op.f('ix_procurement_invoices_status'), table_name='procurement_invoices')
    op.drop_index(op.f('ix_procurement_invoices_goods_receipt_id'), table_name='procurement_invoices')
    op.drop_index(op.f('ix_procurement_invoices_purchase_order_id'), table_name='procurement_invoices')
    op.drop_index(op.f('ix_procurement_invoices_supplier_id'), table_name='procurement_invoices')
    op.drop_index(op.f('ix_procurement_invoices_invoice_number'), table_name='procurement_invoices')
    op.drop_table('procurement_invoices')

    op.drop_index(op.f('ix_goods_receipts_status'), table_name='goods_receipts')
    op.drop_index(op.f('ix_goods_receipts_receipt_number'), table_name='goods_receipts')
    op.drop_index(op.f('ix_goods_receipts_purchase_order_id'), table_name='goods_receipts')
    op.drop_table('goods_receipts')

    op.drop_index(op.f('ix_purchase_order_versions_purchase_order_id'), table_name='purchase_order_versions')
    op.drop_table('purchase_order_versions')

    op.drop_index(op.f('ix_purchase_orders_status'), table_name='purchase_orders')
    op.drop_index(op.f('ix_purchase_orders_order_number'), table_name='purchase_orders')
    op.drop_index(op.f('ix_purchase_orders_supplier_id'), table_name='purchase_orders')
    op.drop_index(op.f('ix_purchase_orders_requisition_id'), table_name='purchase_orders')
    op.drop_table('purchase_orders')

    op.drop_index(op.f('ix_procurement_audit_events_action'), table_name='procurement_audit_events')
    op.drop_index(op.f('ix_procurement_audit_events_requisition_id'), table_name='procurement_audit_events')
    op.drop_table('procurement_audit_events')

    op.drop_index(op.f('ix_procurement_attachments_requisition_id'), table_name='procurement_attachments')
    op.drop_table('procurement_attachments')

    op.drop_index(op.f('ix_procurement_comments_requisition_id'), table_name='procurement_comments')
    op.drop_table('procurement_comments')

    op.drop_index(op.f('ix_procurement_requisition_line_items_requisition_id'), table_name='procurement_requisition_line_items')
    op.drop_table('procurement_requisition_line_items')

    op.drop_index(op.f('ix_procurement_requisitions_tenant_id'), table_name='procurement_requisitions')
    op.drop_index(op.f('ix_procurement_requisitions_supplier_id'), table_name='procurement_requisitions')
    op.drop_index(op.f('ix_procurement_requisitions_lifecycle_status'), table_name='procurement_requisitions')
    op.drop_index(op.f('ix_procurement_requisitions_status'), table_name='procurement_requisitions')
    op.drop_index(op.f('ix_procurement_requisitions_title'), table_name='procurement_requisitions')
    op.drop_table('procurement_requisitions')


