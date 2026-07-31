"""Tests for the AI invoice parsing pipeline (bundle spec sec 2)."""

from decimal import Decimal

from app.services.invoice_parsing import parse_invoice_text

SAMPLE = """INVOICE
Invoice No: INV-2026-0042
Invoice Date: 2026-07-15
Bill From: Acme Industrial Supplies
PO Number: PO-1001
Currency: USD
Terms: Net 30

Widget 10 @ 5.00
Gadget 2 @ 20.00

Subtotal: 90.00
Tax: 7.20
Grand Total: 97.20
"""

INCONSISTENT = """INVOICE
Invoice No: INV-2026-0043
Invoice Date: 2026-07-16
Bill From: Acme Industrial Supplies
PO Number: PO-1002
Currency: USD

Subtotal: 100.00
Tax: 10.00
Grand Total: 200.00
"""

MISSING = """PURCHASE RECEIPT
Some random document with no invoice fields at all.
"""


def test_parse_header_fields():
    parsed = parse_invoice_text(SAMPLE)
    assert parsed.header.invoice_number == "INV-2026-0042"
    assert parsed.header.invoice_date == "2026-07-15"
    assert parsed.header.supplier_name == "Acme Industrial Supplies"
    assert parsed.header.currency in ("USD", "$")
    assert parsed.header.payment_terms == "Net 30"
    assert "PO-1001" in parsed.header.po_numbers
    assert parsed.header.invoice_number_confidence > 0.9


def test_parse_lines_and_totals():
    parsed = parse_invoice_text(SAMPLE)
    assert len(parsed.lines) >= 1
    # First line should be the Widget line with qty 10 and price 5.00.
    widget = parsed.lines[0]
    assert widget.quantity == Decimal("10")
    assert widget.unit_price == Decimal("5.00")
    assert parsed.subtotal == Decimal("90.00")
    assert parsed.tax_total == Decimal("7.20")
    assert parsed.grand_total == Decimal("97.20")
    assert "INCONSISTENT_TOTALS" not in parsed.parsing_metadata["error_flags"]


def test_parse_flags_inconsistent_totals():
    parsed = parse_invoice_text(INCONSISTENT)
    flags = parsed.parsing_metadata["error_flags"]
    assert "INCONSISTENT_TOTALS" in flags


def test_parse_flags_missing_fields():
    parsed = parse_invoice_text(MISSING)
    flags = parsed.parsing_metadata["error_flags"]
    assert any(f.startswith("MISSING_FIELD:") for f in flags)
    assert parsed.header.invoice_number is None
    assert parsed.header.invoice_number_confidence < 0.5
