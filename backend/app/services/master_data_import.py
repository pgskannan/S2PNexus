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


@dataclass
class CategoryRow:
    code: str
    name: str


def parse_categories_csv(csv_text: str) -> list[CategoryRow]:
    reader = _reader_for(csv_text)
    fieldnames = reader.fieldnames or []
    code_col = _find_column(fieldnames, ("code", "category_code", "category"))
    name_col = _find_column(fieldnames, ("name", "category_name", "title"))

    if code_col is None or name_col is None:
        raise MasterDataCSVError([f"Expected columns code and name. Found headers: {fieldnames}"])

    rows: list[CategoryRow] = []
    errors: list[str] = []
    seen_codes: set[str] = set()
    for line_num, raw in enumerate(reader, start=2):
        code = (raw.get(code_col) or "").strip()
        name = (raw.get(name_col) or "").strip()
        if not code and not name:
            continue
        if not code:
            errors.append(f"Row {line_num}: missing category code")
            continue
        if not name:
            errors.append(f"Row {line_num}: missing category name")
            continue
        if code in seen_codes:
            errors.append(f"Row {line_num}: duplicate category code '{code}'")
            continue
        seen_codes.add(code)
        rows.append(CategoryRow(code=code, name=name))

    if errors:
        raise MasterDataCSVError(errors)
    return rows


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


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in ("1", "true", "yes", "y", "t"):
        return True
    if normalized in ("0", "false", "no", "n", "f"):
        return False
    return None


@dataclass
class SupplierHeaderRow:
    external_supplier_code: str | None
    name: str | None
    description: str | None
    contact_email: str | None
    contact_phone: str | None
    address: str | None
    website: str | None
    tax_id: str | None
    legal_name: str | None
    duns_number: str | None
    naics_code: str | None
    vat_number: str | None
    tax_country: str | None
    preferred_payment_method: str | None
    diversity_classifications: str | None
    payment_terms: str | None
    currency: str | None
    is_active: bool | None
    w9_on_file: bool | None


def parse_supplier_headers_csv(csv_text: str) -> list[SupplierHeaderRow]:
    reader = _reader_for(csv_text)
    fieldnames = reader.fieldnames or []
    cols = {
        "external_supplier_code": _find_column(fieldnames, ("external_supplier_code", "external_code", "supplier_external_code", "supplier_code")),
        "name": _find_column(fieldnames, ("name", "supplier_name")),
        "description": _find_column(fieldnames, ("description",)),
        "contact_email": _find_column(fieldnames, ("contact_email", "email")),
        "contact_phone": _find_column(fieldnames, ("contact_phone", "phone")),
        "address": _find_column(fieldnames, ("address", "address_line1")),
        "website": _find_column(fieldnames, ("website", "url")),
        "tax_id": _find_column(fieldnames, ("tax_id", "taxid", "tax")),
        "legal_name": _find_column(fieldnames, ("legal_name", "legalentityname", "legal_entity_name")),
        "duns_number": _find_column(fieldnames, ("duns_number", "duns", "dunsno")),
        "naics_code": _find_column(fieldnames, ("naics_code", "naics")),
        "vat_number": _find_column(fieldnames, ("vat_number", "vat")),
        "tax_country": _find_column(fieldnames, ("tax_country", "taxcountry", "country")),
        "preferred_payment_method": _find_column(fieldnames, ("preferred_payment_method", "payment_method", "preferred_payment")),
        "diversity_classifications": _find_column(fieldnames, ("diversity_classifications", "diversity")),
        "payment_terms": _find_column(fieldnames, ("payment_terms", "terms")),
        "currency": _find_column(fieldnames, ("currency", "currency_code")),
        "is_active": _find_column(fieldnames, ("is_active", "active")),
        "w9_on_file": _find_column(fieldnames, ("w9_on_file", "w9", "w9onfile")),
    }

    rows: list[SupplierHeaderRow] = []
    for raw in reader:
        def get(key: str) -> str | None:
            column = cols[key]
            if column is None:
                return None
            value = (raw.get(column) or "").strip()
            return value or None

        if not any(get(key) for key in ("external_supplier_code", "name", "description", "contact_email", "contact_phone", "address", "website", "tax_id", "legal_name", "duns_number", "naics_code", "vat_number", "tax_country", "preferred_payment_method", "diversity_classifications", "payment_terms", "currency")):
            continue

        rows.append(
            SupplierHeaderRow(
                external_supplier_code=get("external_supplier_code"),
                name=get("name"),
                description=get("description"),
                contact_email=get("contact_email"),
                contact_phone=get("contact_phone"),
                address=get("address"),
                website=get("website"),
                tax_id=get("tax_id"),
                legal_name=get("legal_name"),
                duns_number=get("duns_number"),
                naics_code=get("naics_code"),
                vat_number=get("vat_number"),
                tax_country=get("tax_country"),
                preferred_payment_method=get("preferred_payment_method"),
                diversity_classifications=get("diversity_classifications"),
                payment_terms=get("payment_terms"),
                currency=get("currency"),
                is_active=_parse_bool(get("is_active")),
                w9_on_file=_parse_bool(get("w9_on_file")),
            )
        )

    return rows


def build_supplier_headers_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "external_supplier_code",
            "name",
            "description",
            "contact_email",
            "contact_phone",
            "address",
            "website",
            "tax_id",
            "legal_name",
            "duns_number",
            "naics_code",
            "vat_number",
            "tax_country",
            "preferred_payment_method",
            "diversity_classifications",
            "payment_terms",
            "currency",
            "is_active",
            "w9_on_file",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r.get("external_supplier_code") or "",
                r.get("name") or "",
                r.get("description") or "",
                r.get("contact_email") or "",
                r.get("contact_phone") or "",
                r.get("address") or "",
                r.get("website") or "",
                r.get("tax_id") or "",
                r.get("legal_name") or "",
                r.get("duns_number") or "",
                r.get("naics_code") or "",
                r.get("vat_number") or "",
                r.get("tax_country") or "",
                r.get("preferred_payment_method") or "",
                r.get("diversity_classifications") or "",
                r.get("payment_terms") or "",
                r.get("currency") or "",
                str(bool(r.get("is_active"))).lower() if r.get("is_active") is not None else "",
                str(bool(r.get("w9_on_file"))).lower() if r.get("w9_on_file") is not None else "",
            ]
        )
    return buf.getvalue()


@dataclass
class SupplierAddressRow:
    supplier_id: str | None
    supplier_external_code: str | None
    address_type: str | None
    attention_to: str | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state_province: str | None
    postal_code: str | None
    country: str | None
    phone: str | None
    is_default: bool | None


def parse_supplier_addresses_csv(csv_text: str) -> list[SupplierAddressRow]:
    reader = _reader_for(csv_text)
    fieldnames = reader.fieldnames or []
    cols = {
        "supplier_id": _find_column(fieldnames, ("supplier_id", "supplier")),
        "supplier_external_code": _find_column(fieldnames, ("supplier_external_code", "external_supplier_code", "supplier_code", "external_code")),
        "address_type": _find_column(fieldnames, ("address_type", "type")),
        "attention_to": _find_column(fieldnames, ("attention_to", "attention")),
        "address_line1": _find_column(fieldnames, ("address_line1", "address1", "line1")),
        "address_line2": _find_column(fieldnames, ("address_line2", "address2", "line2")),
        "city": _find_column(fieldnames, ("city",)),
        "state_province": _find_column(fieldnames, ("state_province", "state", "province")),
        "postal_code": _find_column(fieldnames, ("postal_code", "zip", "zipcode")),
        "country": _find_column(fieldnames, ("country",)),
        "phone": _find_column(fieldnames, ("phone",)),
        "is_default": _find_column(fieldnames, ("is_default", "default")),
    }

    rows: list[SupplierAddressRow] = []
    for raw in reader:
        def get(key: str) -> str | None:
            column = cols[key]
            if column is None:
                return None
            value = (raw.get(column) or "").strip()
            return value or None

        if not any(get(key) for key in ("supplier_id", "supplier_external_code", "address_type", "attention_to", "address_line1", "address_line2", "city", "state_province", "postal_code", "country", "phone")):
            continue

        rows.append(
            SupplierAddressRow(
                supplier_id=get("supplier_id"),
                supplier_external_code=get("supplier_external_code"),
                address_type=get("address_type"),
                attention_to=get("attention_to"),
                address_line1=get("address_line1"),
                address_line2=get("address_line2"),
                city=get("city"),
                state_province=get("state_province"),
                postal_code=get("postal_code"),
                country=get("country"),
                phone=get("phone"),
                is_default=_parse_bool(get("is_default")),
            )
        )

    return rows


def build_supplier_addresses_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["supplier_id", "supplier_external_code", "address_type", "attention_to", "address_line1", "address_line2", "city", "state_province", "postal_code", "country", "phone", "is_default"])
    for r in rows:
        writer.writerow(
            [
                r.get("supplier_id") or "",
                r.get("supplier_external_code") or "",
                r.get("address_type") or "",
                r.get("attention_to") or "",
                r.get("address_line1") or "",
                r.get("address_line2") or "",
                r.get("city") or "",
                r.get("state_province") or "",
                r.get("postal_code") or "",
                r.get("country") or "",
                r.get("phone") or "",
                str(bool(r.get("is_default"))).lower() if r.get("is_default") is not None else "",
            ]
        )
    return buf.getvalue()


@dataclass
class SupplierBankAccountRow:
    supplier_id: str | None
    supplier_external_code: str | None
    bank_name: str | None
    account_holder_name: str | None
    account_number: str | None
    iban: str | None
    swift_bic: str | None
    routing_number: str | None
    currency: str | None
    is_primary: bool | None
    intermediary_bank_swift: str | None


def parse_supplier_bank_accounts_csv(csv_text: str) -> list[SupplierBankAccountRow]:
    reader = _reader_for(csv_text)
    fieldnames = reader.fieldnames or []
    cols = {
        "supplier_id": _find_column(fieldnames, ("supplier_id", "supplier")),
        "supplier_external_code": _find_column(fieldnames, ("supplier_external_code", "external_supplier_code", "supplier_code", "external_code")),
        "bank_name": _find_column(fieldnames, ("bank_name", "bank")),
        "account_holder_name": _find_column(fieldnames, ("account_holder_name", "account_holder")),
        "account_number": _find_column(fieldnames, ("account_number", "account")),
        "iban": _find_column(fieldnames, ("iban",)),
        "swift_bic": _find_column(fieldnames, ("swift_bic", "swift", "bic")),
        "routing_number": _find_column(fieldnames, ("routing_number", "routing")),
        "currency": _find_column(fieldnames, ("currency",)),
        "is_primary": _find_column(fieldnames, ("is_primary", "primary")),
        "intermediary_bank_swift": _find_column(fieldnames, ("intermediary_bank_swift", "intermediary")),
    }

    rows: list[SupplierBankAccountRow] = []
    for raw in reader:
        def get(key: str) -> str | None:
            column = cols[key]
            if column is None:
                return None
            value = (raw.get(column) or "").strip()
            return value or None

        if not any(get(key) for key in ("supplier_id", "supplier_external_code", "bank_name", "account_holder_name", "account_number", "iban", "swift_bic", "routing_number", "currency", "intermediary_bank_swift")):
            continue

        rows.append(
            SupplierBankAccountRow(
                supplier_id=get("supplier_id"),
                supplier_external_code=get("supplier_external_code"),
                bank_name=get("bank_name"),
                account_holder_name=get("account_holder_name"),
                account_number=get("account_number"),
                iban=get("iban"),
                swift_bic=get("swift_bic"),
                routing_number=get("routing_number"),
                currency=get("currency"),
                is_primary=_parse_bool(get("is_primary")),
                intermediary_bank_swift=get("intermediary_bank_swift"),
            )
        )

    return rows


def build_supplier_bank_accounts_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["supplier_id", "supplier_external_code", "bank_name", "account_holder_name", "account_number", "iban", "swift_bic", "routing_number", "currency", "is_primary", "intermediary_bank_swift"])
    for r in rows:
        writer.writerow(
            [
                r.get("supplier_id") or "",
                r.get("supplier_external_code") or "",
                r.get("bank_name") or "",
                r.get("account_holder_name") or "",
                r.get("account_number") or "",
                r.get("iban") or "",
                r.get("swift_bic") or "",
                r.get("routing_number") or "",
                r.get("currency") or "",
                str(bool(r.get("is_primary"))).lower() if r.get("is_primary") is not None else "",
                r.get("intermediary_bank_swift") or "",
            ]
        )
    return buf.getvalue()


@dataclass
class DepartmentRow:
    code: str
    name: str | None
    parent_department_id: str | None
    is_active: bool | None


def parse_departments_csv(csv_text: str) -> list[DepartmentRow]:
    reader = _reader_for(csv_text)
    fieldnames = reader.fieldnames or []
    code_col = _find_column(fieldnames, ("code", "department_code"))
    if code_col is None:
        raise MasterDataCSVError([f"Couldn't find a 'code' column. Found headers: {fieldnames}"])

    name_col = _find_column(fieldnames, ("name", "department_name"))
    parent_col = _find_column(fieldnames, ("parent_department_id", "parent_department", "parent_code"))
    active_col = _find_column(fieldnames, ("is_active", "active"))

    rows: list[DepartmentRow] = []
    errors: list[str] = []
    seen_codes: set[str] = set()
    for line_num, raw in enumerate(reader, start=2):
        code = (raw.get(code_col) or "").strip()
        if not code:
            continue
        if code in seen_codes:
            errors.append(f"Row {line_num}: duplicate department code '{code}'")
            continue
        seen_codes.add(code)

        is_active = _parse_bool((raw.get(active_col) or "").strip() if active_col else None)
        if active_col and (raw.get(active_col) or "").strip() and is_active is None:
            errors.append(f"Row {line_num}: invalid is_active value '{raw.get(active_col)}'")
            continue

        rows.append(
            DepartmentRow(
                code=code,
                name=((raw.get(name_col) or "").strip() or None) if name_col else None,
                parent_department_id=((raw.get(parent_col) or "").strip() or None) if parent_col else None,
                is_active=is_active,
            )
        )

    if errors:
        raise MasterDataCSVError(errors)
    return rows


def build_departments_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["code", "name", "parent_department_id", "is_active"])
    for r in rows:
        writer.writerow(
            [
                r.get("code") or "",
                r.get("name") or "",
                r.get("parent_department_id") or "",
                str(bool(r.get("is_active"))).lower() if r.get("is_active") is not None else "",
            ]
        )
    return buf.getvalue()


@dataclass
class CostCenterRow:
    code: str
    name: str | None
    department_id: str | None
    is_active: bool | None


def parse_cost_centers_csv(csv_text: str) -> list[CostCenterRow]:
    reader = _reader_for(csv_text)
    fieldnames = reader.fieldnames or []
    code_col = _find_column(fieldnames, ("code", "cost_center_code"))
    if code_col is None:
        raise MasterDataCSVError([f"Couldn't find a 'code' column. Found headers: {fieldnames}"])

    name_col = _find_column(fieldnames, ("name", "cost_center_name"))
    department_col = _find_column(fieldnames, ("department_id", "department", "department_code"))
    active_col = _find_column(fieldnames, ("is_active", "active"))

    rows: list[CostCenterRow] = []
    errors: list[str] = []
    seen_codes: set[str] = set()
    for line_num, raw in enumerate(reader, start=2):
        code = (raw.get(code_col) or "").strip()
        if not code:
            continue
        if code in seen_codes:
            errors.append(f"Row {line_num}: duplicate cost center code '{code}'")
            continue
        seen_codes.add(code)

        is_active = _parse_bool((raw.get(active_col) or "").strip() if active_col else None)
        if active_col and (raw.get(active_col) or "").strip() and is_active is None:
            errors.append(f"Row {line_num}: invalid is_active value '{raw.get(active_col)}'")
            continue

        rows.append(
            CostCenterRow(
                code=code,
                name=((raw.get(name_col) or "").strip() or None) if name_col else None,
                department_id=((raw.get(department_col) or "").strip() or None) if department_col else None,
                is_active=is_active,
            )
        )

    if errors:
        raise MasterDataCSVError(errors)
    return rows


def build_cost_centers_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["code", "name", "department_id", "is_active"])
    for r in rows:
        writer.writerow(
            [
                r.get("code") or "",
                r.get("name") or "",
                r.get("department_id") or "",
                str(bool(r.get("is_active"))).lower() if r.get("is_active") is not None else "",
            ]
        )
    return buf.getvalue()


@dataclass
class PlantRow:
    code: str
    name: str | None
    address_line1: str | None
    city: str | None
    state_province: str | None
    postal_code: str | None
    country: str | None
    tax_id: str | None
    is_active: bool | None


def parse_plants_csv(csv_text: str) -> list[PlantRow]:
    reader = _reader_for(csv_text)
    fieldnames = reader.fieldnames or []
    code_col = _find_column(fieldnames, ("code", "plant_code"))
    if code_col is None:
        raise MasterDataCSVError([f"Couldn't find a 'code' column. Found headers: {fieldnames}"])

    name_col = _find_column(fieldnames, ("name", "plant_name"))
    line1_col = _find_column(fieldnames, ("address_line1", "address1", "line1"))
    city_col = _find_column(fieldnames, ("city",))
    state_col = _find_column(fieldnames, ("state_province", "state", "province"))
    postal_col = _find_column(fieldnames, ("postal_code", "zip", "zipcode"))
    country_col = _find_column(fieldnames, ("country",))
    tax_id_col = _find_column(fieldnames, ("tax_id", "taxid", "tax"))
    active_col = _find_column(fieldnames, ("is_active", "active"))

    rows: list[PlantRow] = []
    errors: list[str] = []
    seen_codes: set[str] = set()
    for line_num, raw in enumerate(reader, start=2):
        code = (raw.get(code_col) or "").strip()
        if not code:
            continue
        if code in seen_codes:
            errors.append(f"Row {line_num}: duplicate plant code '{code}'")
            continue
        seen_codes.add(code)

        is_active = _parse_bool((raw.get(active_col) or "").strip() if active_col else None)
        if active_col and (raw.get(active_col) or "").strip() and is_active is None:
            errors.append(f"Row {line_num}: invalid is_active value '{raw.get(active_col)}'")
            continue

        rows.append(
            PlantRow(
                code=code,
                name=((raw.get(name_col) or "").strip() or None) if name_col else None,
                address_line1=((raw.get(line1_col) or "").strip() or None) if line1_col else None,
                city=((raw.get(city_col) or "").strip() or None) if city_col else None,
                state_province=((raw.get(state_col) or "").strip() or None) if state_col else None,
                postal_code=((raw.get(postal_col) or "").strip() or None) if postal_col else None,
                country=((raw.get(country_col) or "").strip() or None) if country_col else None,
                tax_id=((raw.get(tax_id_col) or "").strip() or None) if tax_id_col else None,
                is_active=is_active,
            )
        )

    if errors:
        raise MasterDataCSVError(errors)
    return rows


def build_plants_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "code",
        "name",
        "address_line1",
        "city",
        "state_province",
        "postal_code",
        "country",
        "tax_id",
        "is_active",
    ])
    for r in rows:
        writer.writerow(
            [
                r.get("code") or "",
                r.get("name") or "",
                r.get("address_line1") or "",
                r.get("city") or "",
                r.get("state_province") or "",
                r.get("postal_code") or "",
                r.get("country") or "",
                r.get("tax_id") or "",
                str(bool(r.get("is_active"))).lower() if r.get("is_active") is not None else "",
            ]
        )
    return buf.getvalue()
