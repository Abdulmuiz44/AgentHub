from collections.abc import Iterator

from sqlmodel import SQLModel, Session, create_engine


def create_sqlite_engine(path: str = "sqlite:///./agenthub.db"):
    return create_engine(path, connect_args={"check_same_thread": False})


def init_sqlite(path: str = "sqlite:///./agenthub.db"):
    engine = create_sqlite_engine(path)
    SQLModel.metadata.create_all(engine)
    return engine


def get_db_session(engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
