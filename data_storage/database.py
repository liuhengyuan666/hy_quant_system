from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.settings import PostgresConfig, load_postgres_config


class Base(DeclarativeBase):
    pass


_ENGINE_CACHE: dict[str, Engine] = {}
_SESSION_FACTORY_CACHE: dict[str, sessionmaker[Session]] = {}


def get_engine(config: PostgresConfig | None = None) -> Engine:
    cfg = config or load_postgres_config()
    key = cfg.sqlalchemy_url
    engine = _ENGINE_CACHE.get(key)
    if engine is None:
        engine = create_engine(key, pool_pre_ping=True, future=True)
        _ENGINE_CACHE[key] = engine
    return engine


def get_session_factory(config: PostgresConfig | None = None) -> sessionmaker[Session]:
    engine = get_engine(config)
    key = str(engine.url)
    factory = _SESSION_FACTORY_CACHE.get(key)
    if factory is None:
        factory = sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
        _SESSION_FACTORY_CACHE[key] = factory
    return factory


@contextmanager
def session_scope(config: PostgresConfig | None = None):
    factory = get_session_factory(config)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _quoted_identifier(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _ensure_signal_record_schema_compatibility(engine: Engine) -> None:
    inspector = inspect(engine)
    if "signal_record" not in inspector.get_table_names():
        return

    columns = {str(item.get("name")) for item in inspector.get_columns("signal_record")}
    unique_constraints = inspector.get_unique_constraints("signal_record")
    indexes = inspector.get_indexes("signal_record")

    legacy_unique_constraints = [
        str(item.get("name"))
        for item in unique_constraints
        if list(item.get("column_names") or []) == ["date", "symbol", "strategy"] and item.get("name")
    ]
    has_scope_uniqueness = any(
        list(item.get("column_names") or []) == ["date", "symbol", "strategy", "mode", "bar_frequency"]
        for item in unique_constraints
    ) or any(
        bool(item.get("unique")) and list(item.get("column_names") or []) == ["date", "symbol", "strategy", "mode", "bar_frequency"]
        for item in indexes
    )
    has_scope_index = any(
        str(item.get("name")) == "ix_signal_record_scope"
        or list(item.get("column_names") or []) == ["date", "mode", "bar_frequency", "symbol"]
        for item in indexes
    )

    with engine.begin() as connection:
        if "mode" not in columns:
            connection.execute(text("ALTER TABLE signal_record ADD COLUMN mode VARCHAR(16)"))
        if "bar_frequency" not in columns:
            connection.execute(text("ALTER TABLE signal_record ADD COLUMN bar_frequency VARCHAR(8)"))

        connection.execute(text("UPDATE signal_record SET mode = 'eod' WHERE mode IS NULL"))
        connection.execute(text("UPDATE signal_record SET bar_frequency = 'D' WHERE bar_frequency IS NULL"))

        if engine.dialect.name == "postgresql":
            connection.execute(text("ALTER TABLE signal_record ALTER COLUMN mode SET DEFAULT 'eod'"))
            connection.execute(text("ALTER TABLE signal_record ALTER COLUMN bar_frequency SET DEFAULT 'D'"))
            connection.execute(text("ALTER TABLE signal_record ALTER COLUMN mode SET NOT NULL"))
            connection.execute(text("ALTER TABLE signal_record ALTER COLUMN bar_frequency SET NOT NULL"))

            for constraint_name in legacy_unique_constraints:
                connection.execute(
                    text(f"ALTER TABLE signal_record DROP CONSTRAINT IF EXISTS {_quoted_identifier(constraint_name)}")
                )

            if not has_scope_uniqueness:
                connection.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS ux_signal_record_scope "
                        "ON signal_record (date, symbol, strategy, mode, bar_frequency)"
                    )
                )
            if not has_scope_index:
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_signal_record_scope "
                        "ON signal_record (date, mode, bar_frequency, symbol)"
                    )
                )


def init_database(config: PostgresConfig | None = None) -> None:
    import data_storage.models

    engine = get_engine(config)
    Base.metadata.create_all(bind=engine)
    _ensure_signal_record_schema_compatibility(engine)
