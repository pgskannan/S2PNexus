"""Shared CSV parsing for the master-data upload endpoints (commodity codes, GL
accounts, commodity-to-GL mapping) -- see app.routers.gl_accounts and the
commodity-codes mapping upload endpoint in app.routers.commodity.

Deliberately does not touch a database or the filesystem: takes decoded CSV
text, returns plain dataclasses, and raises MasterDataCSVError with a list of
human-readable row problems on anything malformed. Callers decide what to do
with parsed rows (bulk upsert, dry-run preview, etc).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

VALID_SCOPE_LEVELS = ("segment", "family", "class", "commodity")


class MasterDataCSVError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


_COMMODITY_COLUMN_ALIASES = {
    "segment": ("segment", "segment_code"),
    "segment_title": ("segment title", "segment_title", "segmenttitle"),
    "family": ("family", "family_code"),
    "family_title": ("family title", "family_title", "familytitle"),
    "class": ("class", "class_code"),
    "class_title": ("class title", "class_title", "classtitle"),
    "commodity": ("commodity", "commodity_code", "code"),
    "commodity_title": ("commodity title", "commodity_title", "commoditytitle"),
}


def _find_column(fieldnames: list[str], aliases: tuple[str, ...]) -> str | None:
    lower_map = {f.strip().lower(): f for f in fieldnames}
    for alias in aliases:
        if alias in lower_map:
            return lower_map[alias]
    return None


def _reader_for(csv_text: str) -> csv.DictReader:
    return csv.DictReader(io.StringIO(csv_text))


@dataclass
class CommodityCodeRow:
    code: str
    segment_code: str | None
    segment_title: str | None
    family_code: str | None
    family_title: str | None
    class_code: str | None
    class_title: str | None
    commodity_title: str | None


def parse_commodity_codes_csv(csv_text: str) -> list[CommodityCodeRow]:
    reader = _reader_for(csv_text)
    fieldnames = reader.fieldnames or []
    col = {key: _find_column(fieldnames, aliases) for key, aliases in _COMMODITY_COLUMN_ALIASES.items()}

    if col["commodity"] is None:
        raise MasterDataCSVError(
            [f"Couldn't find a commodity/leaf-code column. Found headers: {fieldnames}"]
        )

    rows: list[CommodityCodeRow] = []
    errors: list[str] = []
    seen_codes: set[str] = set()
    for line_num, raw in enumerate(reader, start=2):
        full_code = (raw.get(col["commodity"]) or "").strip()
        if not full_code:
            continue
        full_code = full_code.zfill(8) if full_code.isdigit() else full_code
        if full_code in seen_codes:
            errors.append(f"Row {line_num}: duplicate code '{full_code}'")
            continue
        seen_codes.add(full_code)

        def get(key: str) -> str | None:
            c = col[key]
            if c is None:
                return None
            val = (raw.get(c) or "").strip()
            return val or None

        rows.append(
            CommodityCodeRow(
                code=full_code,
                segment_code=get("segment") or (full_code[:2] if len(full_code) >= 2 else None),
                segment_title=get("segment_title"),
                family_code=get("family") or (full_code[:4] if len(full_code) >= 4 else None),
                family_title=get("family_title"),
                class_code=get("class") or (full_code[:6] if len(full_code) >= 6 else None),
                class_title=get("class_title"),
                commodity_title=get("commodity_title"),
            )
        )

    if errors:
        raise MasterDataCSVError(errors)
    return rows


def build_commodity_codes_csv(rows: list[dict]) -> str:
    """Export helper, symmetric with parse_commodity_codes_csv -- round-trips
    through the exact same column names/order the upload endpoint accepts, so
    a downloaded file can be edited and re-uploaded as-is."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["segment", "segment_title", "family", "family_title", "class", "class_title", "commodity", "commodity_title"]
    )
    for r in rows:
        writer.writerow(
            [
                r.get("segment_code") or "",
                r.get("segment_title") or "",
                r.get("family_code") or "",
                r.get("family_title") or "",
                r.get("class_code") or "",
                r.get("class_title") or "",
                r.get("code") or "",
                r.get("commodity_title") or "",
            ]
        )
    return buf.getvalue()


@dataclass
class GLAccountRow:
    code: str
    description: str | None
    account_type: str | None


def parse_gl_accounts_csv(csv_text: str) -> list[GLAccountRow]:
    reader = _reader_for(csv_text)
    fieldnames = reader.fieldnames or []
    code_col = _find_column(fieldnames, ("code", "gl_account_code", "account_code"))
    if code_col is None:
        raise MasterDataCSVError([f"Couldn't find a 'code' column. Found headers: {fieldnames}"])
    desc_col = _find_column(fieldnames, ("description", "gl_account_description", "account_description"))
    type_col = _find_column(fieldnames, ("account_type", "type"))

    rows: list[GLAccountRow] = []
    errors: list[str] = []
    seen_codes: set[str] = set()
    for line_num, raw in enumerate(reader, start=2):
        code = (raw.get(code_col) or "").strip()
        if not code:
            continue
        if code in seen_codes:
            errors.append(f"Row {line_num}: duplicate GL account code '{code}'")
            continue
        seen_codes.add(code)
        rows.append(
            GLAccountRow(
                code=code,
                description=((raw.get(desc_col) or "").strip() or None) if desc_col else None,
                account_type=((raw.get(type_col) or "").strip() or None) if type_col else None,
            )
        )

    if errors:
        raise MasterDataCSVError(errors)
    return rows


def build_gl_accounts_csv(rows: list[dict]) -> str:
    """Export helper, symmetric with parse_gl_accounts_csv."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["code", "description", "account_type"])
    for r in rows:
        writer.writerow([r.get("code") or "", r.get("description") or "", r.get("account_type") or ""])
    return buf.getvalue()


@dataclass
class GLMappingRow:
    scope_level: str
    scope_code: str
    gl_account_code: str
    cost_center: str | None


def parse_gl_mapping_csv(csv_text: str) -> list[GLMappingRow]:
    reader = _reader_for(csv_text)
    fieldnames = reader.fieldnames or []
    level_col = _find_column(fieldnames, ("scope_level", "level"))
    code_col = _find_column(fieldnames, ("scope_code", "code"))
    gl_col = _find_column(fieldnames, ("gl_account_code", "gl_code", "account_code"))
    cc_col = _find_column(fieldnames, ("cost_center", "costcenter"))

    if level_col is None or code_col is None or gl_col is None:
        raise MasterDataCSVError(
            [
                "Expected columns scope_level, scope_code, gl_account_code (cost_center optional). "
                f"Found headers: {fieldnames}"
            ]
        )

    rows: list[GLMappingRow] = []
    errors: list[str] = []
    for line_num, raw in enumerate(reader, start=2):
        scope_level = (raw.get(level_col) or "").strip().lower()
        scope_code = (raw.get(code_col) or "").strip()
        gl_account_code = (raw.get(gl_col) or "").strip()
        if not scope_level and not scope_code and not gl_account_code:
            continue
        if scope_level not in VALID_SCOPE_LEVELS:
            errors.append(f"Row {line_num}: scope_level must be one of {VALID_SCOPE_LEVELS}, got '{scope_level}'")
            continue
        if not scope_code:
            errors.append(f"Row {line_num}: missing scope_code")
            continue
        if not gl_account_code:
            errors.append(f"Row {line_num}: missing gl_account_code")
            continue
        rows.append(
            GLMappingRow(
                scope_level=scope_level,
                scope_code=scope_code,
                gl_account_code=gl_account_code,
                cost_center=(raw.get(cc_col) or "").strip() or None if cc_col else None,
            )
        )

    if errors:
        raise MasterDataCSVError(errors)
    return rows


def build_gl_mapping_csv(rows: list[dict]) -> str:
    """Export helper, symmetric with parse_gl_mapping_csv."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["scope_level", "scope_code", "gl_account_code", "cost_center"])
    for r in rows:
        writer.writerow(
            [r.get("scope_level") or "", r.get("scope_code") or "", r.get("gl_account_code") or "", r.get("cost_center") or ""]
        )
    return buf.getvalue()
