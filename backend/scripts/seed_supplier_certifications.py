#!/usr/bin/env python3
"""Seed demo supplier certifications for the supplier knowledge graph (HackFW).

Gives every active supplier a realistic, deterministic set of manufacturing
certifications so the graph and the "certified sources" query have something
to show: mostly valid, some expiring inside the 60-day window, a few already
expired. Assignment is derived from a hash of the supplier id, so re-runs and
different environments get the same picture.

Rows are written as shared (tenant_id NULL) certifications, visible to every
tenant -- the same visibility as the supplier master record itself.

USAGE
-----
    cd backend
    python -m scripts.seed_supplier_certifications            # seed
    python -m scripts.seed_supplier_certifications --dry-run  # show plan only

Safe to re-run: a supplier that already has a certificate of a given type
(shared or any tenant's) is skipped for that type.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import pkgutil
from datetime import date, timedelta

import app.models as _models_pkg  # noqa: F401,E402

for _model_module in pkgutil.iter_modules(_models_pkg.__path__):
    __import__(f"app.models.{_model_module.name}")

from sqlalchemy import select  # noqa: E402

from app.database.database import db_manager  # noqa: E402
from app.models.supplier import Supplier  # noqa: E402
from app.models.supplier_certification import SupplierCertification  # noqa: E402

# (cert_type, issuing body, scope) -- the credentials a manufacturing buyer
# actually checks before awarding regulated parts.
CATALOG: list[tuple[str, str, str]] = [
    ("ISO 9001:2015", "BSI", "Quality management system"),
    ("AS9100D", "NQA", "Aerospace quality management"),
    ("IATF 16949", "TUV SUD", "Automotive quality management"),
    ("ISO 14001:2015", "BSI", "Environmental management system"),
    ("ITAR Registration", "U.S. DDTC", "Defense articles manufacturing/export"),
    ("NADCAP Heat Treating", "PRI", "Special process: heat treating"),
    ("ISO 13485:2016", "SGS", "Medical device quality management"),
]


def _plan_for(supplier_id: str, today: date) -> list[dict]:
    digest = hashlib.sha256(supplier_id.encode()).digest()
    plan = []
    # Everyone gets ISO 9001; 2-3 more chosen by hash.
    picks = [0] + sorted({1 + digest[i] % (len(CATALOG) - 1) for i in range(1, 4)})
    for n, idx in enumerate(picks):
        cert_type, body, scope = CATALOG[idx]
        roll = digest[10 + n] % 10
        if roll == 0:
            expires = today - timedelta(days=15 + digest[20 + n] % 90)  # expired
        elif roll == 1:
            expires = today + timedelta(days=10 + digest[20 + n] % 45)  # expiring soon
        else:
            expires = today + timedelta(days=120 + digest[20 + n] % 900)  # valid
        plan.append(
            {
                "cert_type": cert_type,
                "issuing_body": body,
                "scope": scope,
                "certificate_number": f"{cert_type.split()[0].replace(':', '')}-{digest[30 + n % 2]:03d}{digest[n]:03d}",
                "issued_on": expires - timedelta(days=3 * 365),
                "expires_on": expires,
            }
        )
    return plan


async def seed_supplier_certifications(dry_run: bool = False) -> tuple[int, int]:
    today = date.today()
    created = skipped = 0
    async with db_manager.session_factory() as session:
        suppliers = (
            await session.execute(
                select(Supplier).where(Supplier.is_active.is_(True), Supplier.lifecycle_status != "offboarded")
            )
        ).scalars().all()
        existing = {
            (row.supplier_id, row.cert_type)
            for row in (await session.execute(select(SupplierCertification))).scalars().all()
        }
        for s in suppliers:
            for item in _plan_for(str(s.id), today):
                if (s.id, item["cert_type"]) in existing:
                    skipped += 1
                    continue
                created += 1
                if dry_run:
                    print(f"  would add {s.name}: {item['cert_type']} (expires {item['expires_on']})")
                else:
                    session.add(SupplierCertification(supplier_id=s.id, tenant_id=None, **item))
        if not dry_run:
            await session.commit()
    return created, skipped


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    created, skipped = await seed_supplier_certifications(dry_run=args.dry_run)
    verb = "Would create" if args.dry_run else "Created"
    print(f"{verb} {created} certifications ({skipped} already present).")


if __name__ == "__main__":
    asyncio.run(main())
