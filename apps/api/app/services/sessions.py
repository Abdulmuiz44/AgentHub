from collections.abc import Sequence

from sqlmodel import Session as DBSession

from memory import sessions as session_repo
from memory.models import Session


def create_session(db: DBSession, name: str | None = None) -> Session:
    return session_repo.create_session(db, name=name)


def list_sessions(db: DBSession) -> Sequence[Session]:
    return session_repo.list_sessions(db)


def get_session_by_id(db: DBSession, session_id: int) -> Session | None:
    return session_repo.get_session(db, session_id)
