# Integration tests for the master-data CSV upload / delete-all endpoints:
# commodity codes, GL accounts (new master table), and the commodity-to-GL
# mapping that references them. Exercises the CRUD/import layer directly
# (same pattern as test_commodity.py) rather than through FastAPI, since the
# in-memory SQLite fixture here doesn't need auth/session wiring.

import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.services.master_data_import import (
    MasterDataCSVError,
    parse_commodity_codes_csv,
    parse_gl_accounts_csv,
    parse_gl_mapping_csv,
    parse_supplier_addresses_csv,
    parse_supplier_bank_accounts_csv,
    parse_supplier_headers_csv,
)
from app.crud.commodity import (
    bulk_upsert_commodity_account_mappings,
    bulk_upsert_commodity_codes,
    count_commodity_codes,
    delete_all_commodity_account_mappings,
    delete_all_commodity_codes,
    list_commodity_account_mappings,
)
from app.crud.gl_account import bulk_upsert_gl_accounts, delete_all_gl_accounts, list_gl_accounts
from app.crud.supplier import bulk_upsert_supplier_headers, delete_all_suppliers, get_suppliers, get_suppliers_count
from app.crud.supplier_address import (
    bulk_upsert_supplier_addresses,
    count_supplier_addresses,
    delete_all_supplier_addresses,
    list_supplier_addresses,
)
from app.crud.supplier_bank_account import (
    bulk_upsert_supplier_bank_accounts,
    count_supplier_bank_accounts,
    delete_all_supplier_bank_accounts,
    list_supplier_bank_accounts,
)


async def _new_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        tables = [t for t in Base.metadata.sorted_tables if t.name != "chat_messages"]
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return session_factory()


COMMODITY_CSV = (
    "Segment,Segment Title,Family,Family Title,Class,Class Title,Commodity,Commodity Title\n"
    "10,IT Hardware,1001,Computers,100101,Laptops,10010101,Business laptop\n"
    "10,IT Hardware,1001,Computers,100101,Laptops,10010102,Rugged laptop\n"
)

GL_ACCOUNTS_CSV = "code,description,account_type\n6100-IT,IT Hardware Expense,Expense\n"

VALID_MAPPING_CSV = "scope_level,scope_code,gl_account_code,cost_center\nsegment,10,6100-IT,CC-100\n"

INVALID_MAPPING_CSV = "scope_level,scope_code,gl_account_code,cost_center\nsegment,99,NO-SUCH-CODE,CC-999\n"


def test_commodity_code_csv_upload_is_idempotent():
    async def run_test():
        db = await _new_session()
        rows = parse_commodity_codes_csv(COMMODITY_CSV)
        loaded = await bulk_upsert_commodity_codes(db, [r.__dict__ for r in rows])
        assert loaded == 2
        assert await count_commodity_codes(db) == 2

        # re-uploading the same file should update in place, not duplicate
        loaded_again = await bulk_upsert_commodity_codes(db, [r.__dict__ for r in rows])
        assert loaded_again == 2
        assert await count_commodity_codes(db) == 2

    asyncio.run(run_test())


def test_gl_mapping_upload_requires_existing_gl_account():
    async def run_test():
        db = await _new_session()
        gl_rows = parse_gl_accounts_csv(GL_ACCOUNTS_CSV)
        await bulk_upsert_gl_accounts(
            db, tenant_id=None, rows=[(r.code, r.description, r.account_type) for r in gl_rows], updated_by=None
        )

        valid_rows = parse_gl_mapping_csv(VALID_MAPPING_CSV)
        loaded, errors = await bulk_upsert_commodity_account_mappings(
            db, tenant_id=None, rows=[r.__dict__ for r in valid_rows], updated_by=None
        )
        assert loaded == 1
        assert errors == []
        mappings = await list_commodity_account_mappings(db, tenant_id=None)
        assert mappings[0].gl_account_code == "6100-IT"
        assert mappings[0].gl_account_id is not None

        invalid_rows = parse_gl_mapping_csv(INVALID_MAPPING_CSV)
        loaded_bad, errors_bad = await bulk_upsert_commodity_account_mappings(
            db, tenant_id=None, rows=[r.__dict__ for r in invalid_rows], updated_by=None
        )
        assert loaded_bad == 0
        assert len(errors_bad) == 1
        assert "NO-SUCH-CODE" in errors_bad[0]
        # confirm no orphaned mapping was created for the rejected row
        mappings_after = await list_commodity_account_mappings(db, tenant_id=None)
        assert len(mappings_after) == 1

    asyncio.run(run_test())


def test_delete_all_resets_each_dataset_independently():
    async def run_test():
        db = await _new_session()
        rows = parse_commodity_codes_csv(COMMODITY_CSV)
        await bulk_upsert_commodity_codes(db, [r.__dict__ for r in rows])

        gl_rows = parse_gl_accounts_csv(GL_ACCOUNTS_CSV)
        await bulk_upsert_gl_accounts(
            db, tenant_id=None, rows=[(r.code, r.description, r.account_type) for r in gl_rows], updated_by=None
        )
        mapping_rows = parse_gl_mapping_csv(VALID_MAPPING_CSV)
        await bulk_upsert_commodity_account_mappings(
            db, tenant_id=None, rows=[r.__dict__ for r in mapping_rows], updated_by=None
        )

        assert await count_commodity_codes(db) == 2
        assert len(await list_gl_accounts(db, tenant_id=None)) == 1
        assert len(await list_commodity_account_mappings(db, tenant_id=None)) == 1

        deleted_mappings = await delete_all_commodity_account_mappings(db, tenant_id=None)
        assert deleted_mappings == 1
        # commodity codes and GL accounts should be untouched by a mapping-only reset
        assert await count_commodity_codes(db) == 2
        assert len(await list_gl_accounts(db, tenant_id=None)) == 1

        deleted_gl = await delete_all_gl_accounts(db, tenant_id=None)
        assert deleted_gl == 1
        deleted_codes = await delete_all_commodity_codes(db)
        assert deleted_codes == 2
        assert await count_commodity_codes(db) == 0

    asyncio.run(run_test())


def test_malformed_csv_raises_with_row_level_errors():
    bad_csv = "not_a_scope_level,scope_code,gl_account_code\nbogus,10,6100-IT\n"
    try:
        parse_gl_mapping_csv(bad_csv)
        assert False, "expected MasterDataCSVError"
    except MasterDataCSVError as exc:
        assert exc.errors  # header mismatch is reported, not a silent empty result


def test_supplier_master_data_upload_and_reset():
    async def run_test():
        db = await _new_session()

        # headers
        hdr_csv = "Name,External Supplier Code,Legal Name,Tax ID\nAcme Corp,ACME-1,Acme Corporation,TX-1\n"
        hdr_rows = parse_supplier_headers_csv(hdr_csv)
        loaded_hdr = await bulk_upsert_supplier_headers(db, [r.__dict__ for r in hdr_rows], updated_by=None)
        # bulk_upsert_supplier_headers may return (loaded, errors) or just loaded
        if isinstance(loaded_hdr, tuple):
            assert loaded_hdr[0] == 1
        else:
            assert loaded_hdr == 1

        # addresses
        addr_csv = "supplier_external_code,address_type,address_line1,city,country\nACME-1,shipping,123 Main St,Metropolis,US\n"
        addr_rows = parse_supplier_addresses_csv(addr_csv)
        loaded_addr = await bulk_upsert_supplier_addresses(db, [r.__dict__ for r in addr_rows])
        assert loaded_addr == 1
        assert await count_supplier_addresses(db) == 1

        # bank accounts
        bank_csv = "supplier_external_code,bank_name,account_holder_name,account_number,iban,currency\nACME-1,Big Bank,Acme Payments,123456789,GB33BUKB20201555555555,USD\n"
        bank_rows = parse_supplier_bank_accounts_csv(bank_csv)
        loaded_bank = await bulk_upsert_supplier_bank_accounts(db, [r.__dict__ for r in bank_rows], updated_by=None)
        assert loaded_bank == 1
        assert await count_supplier_bank_accounts(db) == 1

        # resets
        deleted_bank = await delete_all_supplier_bank_accounts(db)
        deleted_addr = await delete_all_supplier_addresses(db)
        deleted_suppliers = await delete_all_suppliers(db)
        assert deleted_bank == 1
        assert deleted_addr == 1
        assert deleted_suppliers >= 1

    asyncio.run(run_test())
