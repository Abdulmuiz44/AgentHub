from collections.abc import Iterator

from sqlmodel import Session

from app.config import settings
from memory.db import create_sqlite_engine, init_sqlite

engine = create_sqlite_engine(settings.database_url)


def init_db() -> None:
    init_sqlite(settings.database_url)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
