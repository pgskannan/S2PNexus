#!/usr/bin/env python3
"""Idempotent loader for S2PNexus master data: commodity codes (UNSPSC-shaped
taxonomy) and default GL account mappings.

Why this exists: `commodity_codes` / `commodity_account_mappings` (Phase 0,
see backend/app/models/commodity.py) have existed as empty tables since they
were added -- nothing has ever loaded real rows into either one, locally or
in GCP. This script is the one place that does that load, written so the
exact same command works against both targets: it only ever talks to
whatever DATABASE_URL you give it, it never hardcodes an environment.

USAGE
-----
Local (matches docker-compose.yml's default Postgres):
    DATABASE_URL="postgresql://s2pnexus:s2pnexus@localhost:5432/s2pnexus" \\
        python scripts/load_master_data.py --commodity-csv unspsc_export.csv

GCP: run from Cloud Shell (or wherever you already have network access to
the real DB), with DATABASE_URL set to whatever the backend's actual
connection string is. Per docs/DEPLOY_CHEATSHEET.md, don't paste that value
into chat/AI tooling -- pull it yourself the same way you would to debug a
Cloud Run revision, export it in your own shell, then run:
    DATABASE_URL="$PROD_DATABASE_URL" \\
        python scripts/load_master_data.py --commodity-csv unspsc_export.csv --gl-mapping-csv gl_mappings.csv

Accepts either the app's `postgresql+asyncpg://...` form or a plain
`postgresql://...` DSN -- asyncpg's own connect() only understands the
latter, so the `+asyncpg` driver tag is stripped automatically if present.

INPUT FORMATS
-------------
--commodity-csv: official UNSPSC export column names (case-insensitive,
common alternates tolerated):
    Segment, Segment Title, Family, Family Title, Class, Class Title,
    Commodity, Commodity Title
The full 8-digit leaf code is taken from the "Commodity" column; segment/
family/class codes are derived from it if not given explicitly.

--gl-mapping-csv (optional): one row per default GL mapping, global (not
tenant-specific) scope:
    scope_level (segment|family|class|commodity), scope_code,
    gl_account_code, gl_account_description, cost_center

Both loads upsert on natural key (commodity code; tenant_id=NO_TENANT_ID +
scope_level + scope_code) -- safe to re-run, e.g. to pick up a corrected
export.

This script does NOT include or generate any actual UNSPSC code data --
the full official codeset is licensed by GS1/UNSPSC and isn't something to
source or redistribute here. You provide the CSV; this just loads it.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
import uuid
from dataclasses import dataclass

try:
    import asyncpg
except ImportError:  # pragma: no cover
    print("Missing dependency: pip install asyncpg", file=sys.stderr)
    raise

# Must match app.models.document_numbering.NO_TENANT_ID exactly -- this is the
# sentinel used for "global, not tenant-specific" rows throughout the app.
NO_TENANT_ID = uuid.UUID(int=(2**128 - 1))

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


def _normalize_database_url(url: str) -> str:
    """asyncpg.connect() wants a plain postgresql:// DSN, not SQLAlchemy's +driver form."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _find_column(fieldnames: list[str], aliases: tuple[str, ...]) -> str | None:
    lower_map = {f.strip().lower(): f for f in fieldnames}
    for alias in aliases:
        if alias in lower_map:
            return lower_map[alias]
    return None


@dataclass
class CommodityRow:
    code: str
    segment_code: str | None
    segment_title: str | None
    family_code: str | None
    family_title: str | None
    class_code: str | None
    class_title: str | None
    commodity_title: str | None


def _parse_commodity_csv(path: str) -> list[CommodityRow]:
    rows: list[CommodityRow] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        col = {key: _find_column(fieldnames, aliases) for key, aliases in _COMMODITY_COLUMN_ALIASES.items()}

        if col["commodity"] is None:
            raise ValueError(
                f"Couldn't find a commodity/leaf-code column in {path}. "
                f"Found headers: {fieldnames}. Expected one of {_COMMODITY_COLUMN_ALIASES['commodity']}."
            )

        for raw in reader:
            full_code = (raw.get(col["commodity"]) or "").strip()
            if not full_code:
                continue
            full_code = full_code.zfill(8) if full_code.isdigit() else full_code

            def get(key: str) -> str | None:
                c = col[key]
                if c is None:
                    return None
                val = (raw.get(c) or "").strip()
                return val or None

            rows.append(
                CommodityRow(
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
    return rows


@dataclass
class GLMappingRow:
    scope_level: str
    scope_code: str
    gl_account_code: str | None
    gl_account_description: str | None
    cost_center: str | None


def _parse_gl_mapping_csv(path: str) -> list[GLMappingRow]:
    rows: list[GLMappingRow] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            scope_level = (raw.get("scope_level") or "").strip().lower()
            scope_code = (raw.get("scope_code") or "").strip()
            if scope_level not in ("segment", "family", "class", "commodity") or not scope_code:
                raise ValueError(f"Bad row in {path}: {raw}")
            rows.append(
                GLMappingRow(
                    scope_level=scope_level,
                    scope_code=scope_code,
                    gl_account_code=(raw.get("gl_account_code") or "").strip() or None,
                    gl_account_description=(raw.get("gl_account_description") or "").strip() or None,
                    cost_center=(raw.get("cost_center") or "").strip() or None,
                )
            )
    return rows


async def _load_commodity_codes(conn: asyncpg.Connection, rows: list[CommodityRow]) -> None:
    print(f"Upserting {len(rows)} commodity codes...")
    await conn.executemany(
        """
        INSERT INTO commodity_codes
            (id, code, segment_code, segment_title, family_code, family_title,
             class_code, class_title, commodity_title, is_active, created_at, updated_at)
        VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, true, now(), now())
        ON CONFLICT (code) DO UPDATE SET
            segment_code = EXCLUDED.segment_code,
            segment_title = EXCLUDED.segment_title,
            family_code = EXCLUDED.family_code,
            family_title = EXCLUDED.family_title,
            class_code = EXCLUDED.class_code,
            class_title = EXCLUDED.class_title,
            commodity_title = EXCLUDED.commodity_title,
            updated_at = now()
        """,
        [
            (
                r.code,
                r.segment_code,
                r.segment_title,
                r.family_code,
                r.family_title,
                r.class_code,
                r.class_title,
                r.commodity_title,
            )
            for r in rows
        ],
    )


async def _load_gl_mappings(conn: asyncpg.Connection, rows: list[GLMappingRow]) -> None:
    print(f"Upserting {len(rows)} GL account mappings (global scope)...")
    await conn.executemany(
        """
        INSERT INTO commodity_account_mappings
            (id, tenant_id, scope_level, scope_code, gl_account_code,
             gl_account_description, cost_center, created_at, updated_at)
        VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, now(), now())
        ON CONFLICT (tenant_id, scope_level, scope_code) DO UPDATE SET
            gl_account_code = EXCLUDED.gl_account_code,
            gl_account_description = EXCLUDED.gl_account_description,
            cost_center = EXCLUDED.cost_center,
            updated_at = now()
        """,
        [
            (str(NO_TENANT_ID), r.scope_level, r.scope_code, r.gl_account_code, r.gl_account_description, r.cost_center)
            for r in rows
        ],
    )


async def main_async(args: argparse.Namespace) -> int:
    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        print("Set DATABASE_URL (env var or --database-url) before running this script.", file=sys.stderr)
        return 1
    database_url = _normalize_database_url(database_url)

    commodity_rows = _parse_commodity_csv(args.commodity_csv) if args.commodity_csv else []
    gl_rows = _parse_gl_mapping_csv(args.gl_mapping_csv) if args.gl_mapping_csv else []

    if not commodity_rows and not gl_rows:
        print("Nothing to do -- pass --commodity-csv and/or --gl-mapping-csv.", file=sys.stderr)
        return 1

    conn = await asyncpg.connect(database_url)
    try:
        async with conn.transaction():
            if commodity_rows:
                await _load_commodity_codes(conn, commodity_rows)
            if gl_rows:
                await _load_gl_mappings(conn, gl_rows)
    finally:
        await conn.close()

    print("Done.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=None, help="Postgres DSN; defaults to $DATABASE_URL")
    parser.add_argument("--commodity-csv", default=None, help="Path to a UNSPSC-format commodity code export")
    parser.add_argument("--gl-mapping-csv", default=None, help="Path to a global GL account mapping CSV")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
