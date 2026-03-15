from collections.abc import Iterator
from pathlib import Path
import sqlite3

from sqlmodel import SQLModel, Session, create_engine


RUN_COLUMN_MIGRATIONS = {
    "synthesis_provider": "TEXT",
    "synthesis_model": "TEXT",
    "synthesis_error": "TEXT",
    "synthesis_error_summary": "TEXT",
    "execution_summary": "JSON DEFAULT '{}'",
    "evidence_summary": "JSON DEFAULT '{}'",
}


def create_sqlite_engine(path: str = "sqlite:///./agenthub.db"):
    return create_engine(path, connect_args={"check_same_thread": False})


def _resolve_sqlite_path(path: str) -> Path | None:
    prefix = "sqlite:///"
    if not path.startswith(prefix):
        return None
    return Path(path[len(prefix):]).resolve()


def _ensure_run_columns(path: str) -> None:
    sqlite_path = _resolve_sqlite_path(path)
    if sqlite_path is None or not sqlite_path.exists():
        return

    with sqlite3.connect(sqlite_path) as connection:
        cursor = connection.execute("PRAGMA table_info(run)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        for column_name, column_type in RUN_COLUMN_MIGRATIONS.items():
            if column_name in existing_columns:
                continue
            connection.execute(f"ALTER TABLE run ADD COLUMN {column_name} {column_type}")
        connection.commit()


def init_sqlite(path: str = "sqlite:///./agenthub.db"):
    engine = create_sqlite_engine(path)
    SQLModel.metadata.create_all(engine)
    _ensure_run_columns(path)
    return engine


def get_db_session(engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
