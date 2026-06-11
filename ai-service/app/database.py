import os
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def database_url():
    explicit = os.environ.get("DATABASE_URL")
    if explicit:
        return explicit
    if os.environ.get("USE_SQLITE") == "1":
        return "sqlite:///./db.sqlite3"
    user = os.environ.get("DB_USER", "ai_user")
    password = os.environ.get("DB_PASSWORD", "ai_pass")
    host = os.environ.get("DB_HOST", "ai-db")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME", "ai_db")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


class Base(DeclarativeBase):
    pass


DATABASE_URL = database_url()
ENGINE_OPTIONS = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    ENGINE_OPTIONS["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **ENGINE_OPTIONS)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db():
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _upgrade_behavior_event_schema()


def _upgrade_behavior_event_schema():
    table_name = "app_behaviorevent"
    with engine.begin() as connection:
        inspector = inspect(connection)
        if table_name not in inspector.get_table_names():
            return
        existing = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        timestamp_type = (
            "TIMESTAMP WITH TIME ZONE"
            if connection.dialect.name == "postgresql"
            else "DATETIME"
        )
        additions = {
            "product_id": "INTEGER",
            "domain": "VARCHAR(32) NOT NULL DEFAULT ''",
            "occurred_at": timestamp_type,
            "graph_synced_at": timestamp_type,
            "graph_sync_attempts": "INTEGER NOT NULL DEFAULT 0",
            "graph_sync_error": "TEXT NOT NULL DEFAULT ''",
        }
        for column_name, column_type in additions.items():
            if column_name not in existing:
                connection.exec_driver_sql(
                    f"ALTER TABLE {table_name} "
                    f"ADD COLUMN {column_name} {column_type}"
                )
        for column_name in (
            "product_id",
            "domain",
            "occurred_at",
            "graph_synced_at",
        ):
            connection.exec_driver_sql(
                f"CREATE INDEX IF NOT EXISTS "
                f"ix_{table_name}_{column_name} "
                f"ON {table_name} ({column_name})"
            )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
