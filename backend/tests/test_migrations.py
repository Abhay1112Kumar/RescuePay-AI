"""Alembic migrations must match the ORM models and be reversible."""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.db.base import Base
from app.models import payment  # noqa: F401

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _alembic_config(db_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.cmd_opts = type("Opts", (), {"x": [f"db_url={db_url}"]})()
    return cfg


def _schema(sync_url: str) -> dict[str, dict[str, set[str]]]:
    engine = create_engine(sync_url)
    insp = inspect(engine)
    tables = {}
    for table in insp.get_table_names():
        if table == "alembic_version":
            continue
        tables[table] = {
            "columns": {c["name"] for c in insp.get_columns(table)},
            "indexes": {i["name"] for i in insp.get_indexes(table) if i["name"]},
        }
    engine.dispose()
    return tables


@pytest.fixture
def migrated_db(tmp_path: Path) -> tuple[str, str]:
    path = tmp_path / "migrate.db"
    async_url = f"sqlite+aiosqlite:///{path}"
    command.upgrade(_alembic_config(async_url), "head")
    return async_url, f"sqlite:///{path}"


def test_upgrade_creates_tables_matching_models(migrated_db: tuple[str, str]) -> None:
    _, sync_url = migrated_db
    migrated = _schema(sync_url)

    expected_tables = set(Base.metadata.tables)
    assert set(migrated) == expected_tables

    for name, table in Base.metadata.tables.items():
        assert migrated[name]["columns"] == {c.name for c in table.columns}, name
        model_indexes = {i.name for i in table.indexes}
        assert model_indexes <= migrated[name]["indexes"], name


def test_downgrade_removes_tables(migrated_db: tuple[str, str]) -> None:
    async_url, sync_url = migrated_db
    command.downgrade(_alembic_config(async_url), "base")
    assert _schema(sync_url) == {}


def test_upgrade_is_idempotent_on_migrated_db(migrated_db: tuple[str, str]) -> None:
    async_url, sync_url = migrated_db
    command.upgrade(_alembic_config(async_url), "head")  # no-op, must not raise
    assert "payments" in _schema(sync_url)


def test_legacy_completed_rows_are_quarantined_and_audited(tmp_path: Path):
    path = tmp_path / "legacy.db"
    async_url = f"sqlite+aiosqlite:///{path}"
    cfg = _alembic_config(async_url)
    command.upgrade(cfg, "0001")
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO payments (id, reference_id, currency, amount_minor, status, paypal_order_id, "
                "create_request_id, created_at, updated_at) VALUES ('legacy', 'LEGACY', 'USD', 2500, "
                "'COMPLETED', 'LEGACYORDER1234', 'legacy-key', '2026-10-30T12:00:00', '2026-10-30T12:00:00')"
            )
        )
    command.upgrade(cfg, "head")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT status FROM payments WHERE id = 'legacy'")
            ).scalar_one()
            == "CAPTURE_UNCERTAIN"
        )
        assert (
            connection.execute(
                text(
                    "SELECT event_type FROM payment_events WHERE payment_id = 'legacy'"
                )
            ).scalar_one()
            == "payment.verification_upgrade"
        )
    with pytest.raises(RuntimeError, match="Resolve uncertain payments"):
        command.downgrade(cfg, "0001")
    engine.dispose()
