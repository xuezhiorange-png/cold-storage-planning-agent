"""V0.7 P1 seed_catalog vs seed_demo_coefficients dual-track authority lock."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.coefficients.domain.catalog import COEFFICIENT_CATALOG
from cold_storage.modules.coefficients.infrastructure.database import (
    DatabaseCoefficientService,
)
from cold_storage.modules.coefficients.infrastructure.orm import (
    CoefficientDefinitionRecord,
    CoefficientRevisionRecord,
)
from cold_storage.modules.coefficients.infrastructure.seed import seed_catalog
from cold_storage.modules.projects.infrastructure.orm import Base

DEMO_SEED_CODES: tuple[str, ...] = (
    "area.circulation_allowance_ratio",
    "area.auxiliary_area_ratio",
    "pallet.net_load_kg",
    "pallet.turnover_factor",
    "power.design_margin_ratio",
    "power.standby_ratio",
    "investment.building_unit_cost",
    "investment.refrigeration_equipment_ratio",
    "investment.electrical_installation_ratio",
    "investment.other_expenses_ratio",
)


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    coefficient_tables = [
        t for name, t in Base.metadata.tables.items() if name.startswith("coefficient_")
    ]
    Base.metadata.create_all(eng, tables=coefficient_tables)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_service(engine):
    return DatabaseCoefficientService(engine)


def test_seed_catalog_populates_manifest_with_standard_approved_placeholder(engine) -> None:
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        seed_catalog(session)
    with session_factory() as session:
        definitions = session.scalars(select(CoefficientDefinitionRecord)).all()
        assert len(definitions) == len(COEFFICIENT_CATALOG)
        revisions = session.scalars(select(CoefficientRevisionRecord)).all()
        assert len(revisions) == len(COEFFICIENT_CATALOG)
        for revision in revisions:
            assert revision.source_type == "standard"
            assert revision.status == "approved"
            assert revision.value_decimal == "1.0"


def test_seed_demo_coefficients_populates_unverified_demo_track(
    db_service: DatabaseCoefficientService,
) -> None:
    revisions = db_service.seed_demo_coefficients()
    assert len(revisions) == 10
    for definition in db_service.list_definitions():
        stored_revisions = db_service.list_revisions(definition.id)
        assert len(stored_revisions) == 1
        revision = stored_revisions[0]
        assert revision.source_type == "demo"
        assert revision.status == "unverified"


def test_e7_catalog_and_demo_seed_share_codes_but_remain_separate_tracks() -> None:
    catalog_codes = {entry["code"] for entry in COEFFICIENT_CATALOG}
    assert catalog_codes == set(DEMO_SEED_CODES)
    electrical_catalog = next(
        entry for entry in COEFFICIENT_CATALOG
        if entry["code"] == "investment.electrical_installation_ratio"
    )
    assert electrical_catalog["canonical_unit"] == "ratio"


def test_seed_catalog_then_demo_seed_fails_closed_on_duplicate_codes(
    engine,
    db_service: DatabaseCoefficientService,
) -> None:
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        seed_catalog(session)
    from cold_storage.modules.coefficients.domain.exceptions import (
        DuplicateCoefficientCodeError,
    )

    with pytest.raises(DuplicateCoefficientCodeError):
        db_service.seed_demo_coefficients()


def test_demo_seed_electrical_installation_value_locked(
    db_service: DatabaseCoefficientService,
) -> None:
    db_service.seed_demo_coefficients()
    definition = db_service.get_definition_by_code("investment.electrical_installation_ratio")
    revision = db_service.list_revisions(definition.id)[0]
    assert revision.value_decimal == Decimal("650")
    assert revision.unit == "CNY/m²"
    assert revision.source_type == "demo"
    assert revision.status == "unverified"
