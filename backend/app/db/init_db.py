# File Path: backend/app/db/init_db.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.partitions import drop_expired_usage_partitions, ensure_usage_event_partitions
from app.db.seed import seed_base_data
from app.db.session import SessionLocal, engine


_MIGRATION_LOCK_KEY = 91526001


def _build_alembic_config() -> Config:
    backend_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    return cfg


def _run_migrations() -> None:
    cfg = _build_alembic_config()

    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:lock_key)"), {"lock_key": _MIGRATION_LOCK_KEY})
        try:
            cfg.attributes["connection"] = connection
            inspector = inspect(connection)
            has_version_table = inspector.has_table("alembic_version")
            has_legacy_schema = any(
                inspector.has_table(table_name)
                for table_name in ("users", "departments", "providers", "models")
            )

            if has_version_table:
                command.upgrade(cfg, "head")
                return

            if has_legacy_schema:
                command.stamp(cfg, "head")
                return

            command.upgrade(cfg, "head")
        finally:
            cfg.attributes.pop("connection", None)
            connection.execute(text("SELECT pg_advisory_unlock(:lock_key)"), {"lock_key": _MIGRATION_LOCK_KEY})


def init_db() -> None:
    _run_migrations()
    ensure_usage_event_partitions(engine=engine, future_months=3)
    drop_expired_usage_partitions(engine=engine, retention_months=12)
    session = SessionLocal()
    try:
        seed_base_data(session)
    except SQLAlchemyError:
        session.rollback()
        raise
    finally:
        session.close()
