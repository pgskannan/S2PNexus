"""add purchase order line items and po fields

Revision ID: b3c9f1a2d4e5
Revises: a1b2c3d4e5f7
Create Date: 2026-07-27 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b3c9f1a2d4e5'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'purchase_order_line_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('purchase_order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('purchase_orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('line_number', sa.Integer(), nullable=False),
        sa.Column('requisition_line_item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('procurement_requisition_line_items.id', ondelete='SET NULL')),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('commodity_code_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('commodity_codes.id', ondelete='SET NULL')),
        sa.Column('commodity_code_free_text', sa.String(length=255)),
        sa.Column('quantity', sa.Numeric(12,2), nullable=False, server_default='1'),
        sa.Column('unit_of_measure', sa.String(length=20)),
        sa.Column('unit_price', sa.Numeric(12,2)),
        sa.Column('line_total', sa.Numeric(12,2)),
        sa.Column('tax_code', sa.String(length=50)),
        sa.Column('tax_amount', sa.Numeric(12,2)),
        sa.Column('account_code', sa.String(length=100)),
        sa.Column('account_code_is_override', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('allocated_shipping_amount', sa.Numeric(12,2), server_default='0'),
        sa.Column('need_by_date', sa.DateTime(timezone=True)),
        sa.Column('promised_date', sa.DateTime(timezone=True)),
        sa.Column('notes', sa.Text()),
        sa.Column('weight', sa.Numeric(12,2)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    op.add_column('purchase_orders', sa.Column('subtotal', sa.Numeric(12,2)))
    op.add_column('purchase_orders', sa.Column('tax_total', sa.Numeric(12,2)))
    op.add_column('purchase_orders', sa.Column('shipping_amount', sa.Numeric(12,2)))
    op.add_column('purchase_orders', sa.Column('grand_total', sa.Numeric(12,2)))
    op.add_column('purchase_orders', sa.Column('incoterms', sa.String(length=50)))
    op.add_column('purchase_orders', sa.Column('payment_terms', sa.String(length=100)))
    op.add_column('purchase_orders', sa.Column('buyer_contact_id', postgresql.UUID(as_uuid=True)))
    op.add_column('purchase_orders', sa.Column('supplier_contact_email', sa.String(length=255)))
    op.add_column('purchase_orders', sa.Column('acknowledgment_status', sa.String(length=50), nullable=False, server_default='pending'))
    op.add_column('purchase_orders', sa.Column('acknowledged_at', sa.DateTime(timezone=True)))
    op.add_column('purchase_orders', sa.Column('acknowledged_notes', sa.Text()))
    op.add_column('purchase_orders', sa.Column('lifecycle_status', sa.String(length=50), nullable=False, server_default='draft'))
    op.add_column('purchase_orders', sa.Column('ship_to_address_id', postgresql.UUID(as_uuid=True)))
    op.add_column('purchase_orders', sa.Column('bill_to_address_id', postgresql.UUID(as_uuid=True)))
    op.add_column('purchase_orders', sa.Column('ship_to_name', sa.String(length=255)))
    op.add_column('purchase_orders', sa.Column('ship_to_address_line1', sa.String(length=255)))
    op.add_column('purchase_orders', sa.Column('ship_to_city', sa.String(length=100)))
    op.add_column('purchase_orders', sa.Column('bill_to_name', sa.String(length=255)))
    op.add_column('purchase_orders', sa.Column('bill_to_address_line1', sa.String(length=255)))
    op.add_column('purchase_orders', sa.Column('bill_to_city', sa.String(length=100)))
    op.add_column('purchase_orders', sa.Column('shipping_allocation_method', sa.String(length=50), nullable=False, server_default='prorate_by_value'))


def downgrade():
    op.drop_column('purchase_orders', 'shipping_allocation_method')
    op.drop_column('purchase_orders', 'bill_to_city')
    op.drop_column('purchase_orders', 'bill_to_address_line1')
    op.drop_column('purchase_orders', 'bill_to_name')
    op.drop_column('purchase_orders', 'ship_to_city')
    op.drop_column('purchase_orders', 'ship_to_address_line1')
    op.drop_column('purchase_orders', 'ship_to_name')
    op.drop_column('purchase_orders', 'bill_to_address_id')
    op.drop_column('purchase_orders', 'ship_to_address_id')
    op.drop_column('purchase_orders', 'lifecycle_status')
    op.drop_column('purchase_orders', 'acknowledged_notes')
    op.drop_column('purchase_orders', 'acknowledged_at')
    op.drop_column('purchase_orders', 'acknowledgment_status')
    op.drop_column('purchase_orders', 'supplier_contact_email')
    op.drop_column('purchase_orders', 'buyer_contact_id')
    op.drop_column('purchase_orders', 'payment_terms')
    op.drop_column('purchase_orders', 'incoterms')
    op.drop_column('purchase_orders', 'grand_total')
    op.drop_column('purchase_orders', 'shipping_amount')
    op.drop_column('purchase_orders', 'tax_total')
    op.drop_column('purchase_orders', 'subtotal')
    op.drop_table('purchase_order_line_items')
