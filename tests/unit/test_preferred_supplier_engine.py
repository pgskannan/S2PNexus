"""Phase 3 unit tests: Preferred Supplier composite engine (spec Section 17).

Every threshold boundary, the Strategic contract-coverage AND, the Blocked
risk OR (high risk blocks even a great composite), the risk inversion, and
the missing-component renormalization. Pure functions -- no DB -- plus one
in-memory-DB test for recompute_preferred_status upsert + override behavior.
"""

import asyncio
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.services.preferred_supplier import (
    PreferredScoreInputs,
    classify,
    compute_preferred_score,
    recompute_preferred_status,
    spend_tier_normalized,
)


def full_inputs(**overrides) -> PreferredScoreInputs:
    """A baseline supplier with all four components present. Defaults chosen
    so the composite is easy to steer from tests."""
    defaults = dict(
        qualification_score=80,
        performance_score=Decimal("80"),
        risk_score=20,  # -> favorability 80
        spend_tier=3,  # -> 75
        has_active_contract=False,
    )
    defaults.update(overrides)
    return PreferredScoreInputs(**defaults)


class TestCompositeFormula:
    def test_exact_weights_and_risk_inversion(self):
        # 0.30*80 + 0.30*80 + 0.20*(100-20) + 0.20*75 = 24+24+16+15 = 79
        assert compute_preferred_score(full_inputs()) == Decimal("79.00")

    def test_high_risk_lowers_score(self):
        low_risk = compute_preferred_score(full_inputs(risk_score=10))
        high_risk = compute_preferred_score(full_inputs(risk_score=90))
        assert low_risk > high_risk  # literal 0.20*Risk transcription would invert this

    def test_spend_tier_normalization(self):
        assert spend_tier_normalized(1) == Decimal("25")
        assert spend_tier_normalized(4) == Decimal("100")
        assert spend_tier_normalized(0) == Decimal("25")  # clamped
        assert spend_tier_normalized(9) == Decimal("100")  # clamped

    def test_missing_qualification_renormalizes(self):
        # Without qualification: (0.30*80 + 0.20*80 + 0.20*75) / 0.70 = 55/0.7
        score = compute_preferred_score(full_inputs(qualification_score=None))
        assert score == (Decimal("55") / Decimal("0.70")).quantize(Decimal("0.01"))

    def test_all_missing_returns_none(self):
        assert compute_preferred_score(PreferredScoreInputs()) is None


class TestClassifyThresholds:
    def _status_for_composite(self, target: Decimal, **overrides) -> str:
        """Classify with a directly supplied composite (bypassing formula) to
        pin threshold boundaries exactly."""
        status, _ = classify(full_inputs(**overrides), target)
        return status

    def test_preferred_boundary_84_99_vs_85(self):
        assert self._status_for_composite(Decimal("84.99")) == "approved"
        assert self._status_for_composite(Decimal("85.00")) == "preferred"

    def test_strategic_requires_contract_AND_90(self):
        # >= 90 without a contract is preferred, not strategic:
        assert self._status_for_composite(Decimal("90.00")) == "preferred"
        assert self._status_for_composite(Decimal("90.00"), has_active_contract=True) == "strategic"
        assert self._status_for_composite(Decimal("89.99"), has_active_contract=True) == "preferred"

    def test_approved_boundary(self):
        assert self._status_for_composite(Decimal("70.00")) == "approved"
        assert self._status_for_composite(Decimal("69.99")) == "none"  # 60-70 gap: neither approved nor blocked

    def test_blocked_boundary(self):
        assert self._status_for_composite(Decimal("60.00")) == "none"
        assert self._status_for_composite(Decimal("59.99")) == "blocked"

    def test_high_risk_blocks_despite_great_composite(self):
        """The OR in 'Blocked < 60 OR High Risk' is load-bearing."""
        status, reason = classify(full_inputs(risk_score=81), Decimal("95.00"))
        assert status == "blocked"
        assert "risk" in reason

    def test_risk_80_exactly_is_not_blocked(self):
        assert self._status_for_composite(Decimal("85.00"), risk_score=80) == "preferred"

    def test_low_performance_blocks(self):
        status, _ = classify(full_inputs(performance_score=Decimal("59.99")), Decimal("75.00"))
        assert status == "blocked"

    def test_compliance_violation_blocks(self):
        status, _ = classify(full_inputs(compliance_violation=True), Decimal("95.00"))
        assert status == "blocked"

    def test_no_data_is_none_not_blocked(self):
        status, _ = classify(PreferredScoreInputs(), None)
        assert status == "none"


class TestAutoPreferred:
    def test_all_gates_met_promotes_at_composite_below_85(self):
        """Auto-preferred can promote a supplier whose composite alone
        wouldn't reach the preferred band."""
        inputs = full_inputs(
            qualification_score=90,
            performance_score=Decimal("90"),
            risk_score=20,
            spend_tier=3,
        )
        composite = compute_preferred_score(inputs)
        # 0.30*90 + 0.30*90 + 0.20*80 + 0.20*75 = 27+27+16+15 = 85 -> already
        # preferred by threshold; force the interesting case with tier 3 and
        # higher risk still inside the auto gate:
        inputs2 = full_inputs(
            qualification_score=90,
            performance_score=Decimal("90"),
            risk_score=20,
            spend_tier=3,
        )
        status, reason = classify(inputs2, Decimal("84.00"))
        assert status == "preferred"
        assert "auto-preferred" in reason

    def test_one_gate_missed_falls_back_to_thresholds(self):
        inputs = full_inputs(
            qualification_score=90,
            performance_score=Decimal("90"),
            risk_score=21,  # misses the <= 20 gate
            spend_tier=3,
        )
        status, reason = classify(inputs, Decimal("84.00"))
        assert status == "approved"
        assert "auto-preferred" not in reason

    def test_auto_preferred_does_not_shadow_strategic(self):
        inputs = full_inputs(
            qualification_score=95,
            performance_score=Decimal("95"),
            risk_score=10,
            spend_tier=4,
            has_active_contract=True,
        )
        status, _ = classify(inputs, Decimal("93.00"))
        assert status == "strategic"


class TestRecomputeUpsert:
    def test_recompute_creates_updates_and_respects_override(self):
        async def run_test():
            from app.database.database import Base
            from app.models.supplier import Supplier
            from app.models.user import User, UserRole

            engine = create_async_engine(
                "sqlite+aiosqlite:///:memory:",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
            async with engine.begin() as conn:
                tables = [t for t in Base.metadata.sorted_tables if t.name != "chat_messages"]
                await conn.run_sync(Base.metadata.create_all, tables=tables)
            db: AsyncSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)()

            user = User(
                email=f"{uuid4()}@example.com", full_name="U", hashed_password="x",
                role=UserRole.ADMINISTRATOR, is_active=True, is_superuser=True,
            )
            db.add(user)
            await db.flush()
            supplier = Supplier(name="Acme", created_by=user.id, current_risk_score=30, current_risk_level="medium")
            db.add(supplier)
            await db.commit()
            await db.refresh(supplier)

            # First recompute creates the row. Only risk + spend tier (1, no
            # invoices) have data: composite = (0.20*70 + 0.20*25) / 0.40 = 47.50
            row = await recompute_preferred_status(db, supplier.id)
            assert row.composite_score == Decimal("47.50")
            assert row.preferred_status == "blocked"  # < 60
            assert row.performance_score is None
            first_id = row.id

            # Second recompute updates the same row (upsert, no duplicates).
            row2 = await recompute_preferred_status(db, supplier.id)
            assert row2.id == first_id

            # An active override survives recompute: status untouched,
            # components refreshed, reason records both sides.
            row2.override_flag = True
            row2.override_reason = "pilot exception"
            row2.preferred_status = "approved"
            await db.commit()
            row3 = await recompute_preferred_status(db, supplier.id)
            assert row3.preferred_status == "approved"  # override preserved
            assert row3.override_flag is True
            assert "override active" in row3.classification_reason
            assert "pilot exception" in row3.classification_reason

        asyncio.run(run_test())
