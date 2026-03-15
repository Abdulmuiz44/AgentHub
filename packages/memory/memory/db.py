from collections.abc import Iterator
from pathlib import Path
import sqlite3

from sqlmodel import SQLModel, Session, create_engine


RUN_COLUMN_MIGRATIONS = {
    "synthesis_mode": "TEXT",
    "synthesis_status": "TEXT",
    "synthesis_error_summary": "TEXT",
    "execution_summary": "JSON DEFAULT '{}'",
    "evidence_summary": "JSON DEFAULT '{}'",
}

SKILL_COLUMN_MIGRATIONS = {
    "description": "TEXT DEFAULT ''",
    "runtime_type": "TEXT DEFAULT 'native_python'",
    "is_builtin": "BOOLEAN DEFAULT 0",
    "scopes": "JSON DEFAULT '[]'",
    "tags": "JSON DEFAULT '[]'",
    "manifest_json": "JSON DEFAULT '{}'",
    "install_source": "TEXT",
    "last_test_status": "TEXT",
    "last_test_summary": "TEXT",
    "last_tested_at": "TIMESTAMP",
    "created_at": "TIMESTAMP",
    "updated_at": "TIMESTAMP",
}


def create_sqlite_engine(path: str = "sqlite:///./agenthub.db"):
    return create_engine(path, connect_args={"check_same_thread": False})


def _resolve_sqlite_path(path: str) -> Path | None:
    prefix = "sqlite:///"
    if not path.startswith(prefix):
        return None
    return Path(path[len(prefix):]).resolve()


def _ensure_columns(path: str, table_name: str, migrations: dict[str, str]) -> None:
    sqlite_path = _resolve_sqlite_path(path)
    if sqlite_path is None or not sqlite_path.exists():
        return

    with sqlite3.connect(sqlite_path) as connection:
        cursor = connection.execute(f"PRAGMA table_info({table_name})")
        existing_columns = {row[1] for row in cursor.fetchall()}
        for column_name, column_type in migrations.items():
            if column_name in existing_columns:
                continue
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        connection.commit()


def init_sqlite(path: str = "sqlite:///./agenthub.db"):
    engine = create_sqlite_engine(path)
    SQLModel.metadata.create_all(engine)
    _ensure_columns(path, "run", RUN_COLUMN_MIGRATIONS)
    _ensure_columns(path, "skilldefinition", SKILL_COLUMN_MIGRATIONS)
    return engine


def get_db_session(engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
