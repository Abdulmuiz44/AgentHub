from collections.abc import Sequence

from sqlmodel import Session as DBSession, select

from .models import Session


def create_session(db: DBSession, name: str | None = None) -> Session:
    record = Session(name=name)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_sessions(db: DBSession) -> Sequence[Session]:
    return db.exec(select(Session)).all()


def get_session(db: DBSession, session_id: int) -> Session | None:
    return db.get(Session, session_id)
