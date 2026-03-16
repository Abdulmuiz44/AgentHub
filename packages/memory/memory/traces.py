from sqlmodel import Session as DBSession, select

from .models import TraceEventRecord


def add_trace_event(db: DBSession, run_id: int, event_type: str, payload: str = "{}") -> TraceEventRecord:
    event = TraceEventRecord(run_id=run_id, event_type=event_type, payload=payload)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_trace_events(db: DBSession, run_id: int, *, after_id: int = 0) -> list[TraceEventRecord]:
    statement = select(TraceEventRecord).where(TraceEventRecord.run_id == run_id)
    if after_id > 0:
        statement = statement.where(TraceEventRecord.id > after_id)
    statement = statement.order_by(TraceEventRecord.id)
    return db.exec(statement).all()
