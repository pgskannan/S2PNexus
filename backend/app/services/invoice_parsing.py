"""AI invoice parsing pipeline (bundle spec sec 2).

Pipeline: normalize -> (OCR/PDF text extraction) -> field detection -> semantic
parsing -> post-processing/normalization -> confidence & error handling.

The default engine is a deterministic, regex + line-heuristic rule-based parser
so it is fully testable offline and never hallucinates. The `llm_provider`
hook (ollama/langchain) can be injected to replace the semantic parsing stage;
when no provider is available the rule-based parser is used. Every extracted
field carries a confidence (0-1) and the result includes ParsingMetadata with
error flags (LOW_CONFIDENCE / MISSING_FIELD / INCONSISTENT_TOTALS).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional

from app.schemas.invoice_parsing import (
    ParsedInvoice,
    ParsedInvoiceHeader,
    ParsedInvoiceLine,
)

_MODEL_VERSION = "rule-based-1.0"

_RE_INVOICE_NUMBER = re.compile(
    r"(?:invoice\s*(?:no\.?|number|#)\s*[:#-]?\s*|invoice\s*[:#]\s*)([A-Z0-9][A-Z0-9\-/]{2,})", re.IGNORECASE
)
_RE_PO_NUMBER = re.compile(
    r"(?:\bPO\s*(?:no\.?|number|#)\s*[:#-]?\s*|\bPO\s*[:#]\s*)([A-Z0-9][A-Z0-9\-/]{2,})", re.IGNORECASE
)
_RE_DATE = re.compile(r"(\d{1,4}[-/]\d{1,2}[-/]\d{1,4})")
_RE_CURRENCY = re.compile(r"\b(USD|EUR|GBP|INR|JPY|AUD|CAD)\b|([$€£₹¥])")
_RE_PAYMENT_TERMS = re.compile(r"\b(net\s*\d+|due\s*on\s+(receipt|invoice)|eom|30\s*days)\b", re.IGNORECASE)
_RE_SUPPLIER = re.compile(r"(?:supplier|bill\s*from|vendor|from)\s*[:\-]?\s*([A-Za-z0-9&.\- ]{2,60})", re.IGNORECASE)
_RE_AMOUNT = re.compile(r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)")
_RE_TOTAL = re.compile(
    r"(?:grand\s*total|amount\s*due|\btotal)\s*[:\-$]?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", re.IGNORECASE
)
_RE_SUBTOTAL = re.compile(r"(?:subtotal|sub\s*total)\s*[:\-$]?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", re.IGNORECASE)
_RE_TAX = re.compile(r"(?:tax|vat|gst)\s*(?:total)?\s*[:\-$]?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", re.IGNORECASE)
_RE_UOM = re.compile(r"\b(ea|each|box|case|pallet|kg|lb|hr|hour|day|pcs|unit)\b", re.IGNORECASE)


def _money(raw: Optional[str]) -> Optional[Decimal]:
    if not raw:
        return None
    cleaned = raw.replace(",", "").strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _conf(found: bool, missing_is_low: bool = True) -> float:
    return 0.95 if found else (0.10 if missing_is_low else 0.0)


def _normalize_lines(text: str) -> list[str]:
    """Split raw text into non-empty, non-header lines."""
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _extract_line_items(lines: list[str]) -> list[ParsedInvoiceLine]:
    """Heuristic line extraction: a line that starts with a description token
    and contains a quantity and a price (e.g. 'Widget 10 @ 5.00' or
    'Widget 10 5.00'). Returns at most the parsed candidates."""
    parsed: list[ParsedInvoiceLine] = []
    for ln in lines:
        # Skip obvious header/total lines.
        if re.search(r"(invoice|total|subtotal|tax|po\s*no|date|supplier|page\s*\d)", ln, re.IGNORECASE):
            continue
        amounts = _RE_AMOUNT.findall(ln)
        if len(amounts) < 2:
            continue
        # Description = text before the last two numeric tokens.
        tokens = ln.split()
        if len(tokens) < 3:
            continue
        qty = _money(amounts[-2])
        price = _money(amounts[-1])
        desc = " ".join(tokens[: max(1, len(tokens) - 2)])
        if qty is None or price is None:
            continue
        uom_match = _RE_UOM.search(ln)
        parsed.append(
            ParsedInvoiceLine(
                description=desc,
                description_confidence=0.8,
                quantity=qty,
                quantity_confidence=0.85,
                unit_price=price,
                unit_price_confidence=0.85,
                uom=uom_match.group(1).lower() if uom_match else None,
                uom_confidence=0.7 if uom_match else 0.1,
            )
        )
    return parsed[:20]


def _detect_flags(parsed: ParsedInvoice) -> list[str]:
    flags: list[str] = []
    header = parsed.header
    for field, conf in [
        ("invoice_number", header.invoice_number_confidence),
        ("invoice_date", header.invoice_date_confidence),
        ("supplier_name", header.supplier_name_confidence),
        ("currency", header.currency_confidence),
    ]:
        if getattr(header, field) is None:
            flags.append(f"MISSING_FIELD:{field}")
        elif conf < 0.5:
            flags.append(f"LOW_CONFIDENCE:{field}")
    if parsed.subtotal is not None and parsed.tax_total is not None and parsed.grand_total is not None:
        expected = parsed.subtotal + parsed.tax_total
        if abs(expected - parsed.grand_total) > Decimal("0.01"):
            flags.append("INCONSISTENT_TOTALS")
    return flags


def parse_invoice_text(text: str, *, source_document_id: Optional[str] = None) -> ParsedInvoice:
    """Rule-based parsing stage (deterministic, offline)."""
    lines = _normalize_lines(text)
    invoice_no = _RE_INVOICE_NUMBER.search(text)
    po_numbers = [m.group(1) for m in _RE_PO_NUMBER.finditer(text)]
    date_match = _RE_DATE.search(text)
    currency_match = _RE_CURRENCY.search(text)
    payment_match = _RE_PAYMENT_TERMS.search(text)
    supplier_match = _RE_SUPPLIER.search(text)
    total_match = _RE_TOTAL.search(text)
    subtotal_match = _RE_SUBTOTAL.search(text)
    tax_match = _RE_TAX.search(text)

    header = ParsedInvoiceHeader(
        invoice_number=invoice_no.group(1) if invoice_no else None,
        invoice_number_confidence=_conf(invoice_no is not None),
        invoice_date=date_match.group(1) if date_match else None,
        invoice_date_confidence=_conf(date_match is not None),
        supplier_name=supplier_match.group(1).strip() if supplier_match else None,
        supplier_name_confidence=_conf(supplier_match is not None),
        currency=(currency_match.group(1) or currency_match.group(2) or None) if currency_match else None,
        currency_confidence=_conf(currency_match is not None),
        payment_terms=payment_match.group(1) if payment_match else None,
        payment_terms_confidence=_conf(payment_match is not None),
        po_numbers=po_numbers,
    )

    parsed = ParsedInvoice(
        source_document_id=source_document_id,
        header=header,
        lines=_extract_line_items(lines),
        subtotal=_money(subtotal_match.group(1)) if subtotal_match else None,
        tax_total=_money(tax_match.group(1)) if tax_match else None,
        grand_total=_money(total_match.group(1)) if total_match else None,
        parsing_metadata={
            "model_version": _MODEL_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error_flags": [],
        },
    )
    parsed.parsing_metadata["error_flags"] = _detect_flags(parsed)
    return parsed


def parse_invoice(
    text: str,
    *,
    source_document_id: Optional[str] = None,
    llm_provider: Optional[Callable[[str], dict[str, Any]]] = None,
) -> ParsedInvoice:
    """Full pipeline entry point. If an `llm_provider` is supplied it may return
    a dict matching ParsedInvoice shape (semantic stage override); otherwise the
    deterministic rule-based parser runs."""
    if llm_provider is not None:
        try:
            payload = llm_provider(text)
            if isinstance(payload, dict):
                return ParsedInvoice.model_validate(payload)
        except Exception:
            pass  # fall through to rule-based parser on any LLM failure
    return parse_invoice_text(text, source_document_id=source_document_id)
