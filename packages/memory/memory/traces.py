from sqlmodel import Session as DBSession, select

from .models import TraceEventRecord


def add_trace_event(db: DBSession, run_id: int, event_type: str, payload: str = "{}") -> TraceEventRecord:
    event = TraceEventRecord(run_id=run_id, event_type=event_type, payload=payload)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_trace_events(db: DBSession, run_id: int) -> list[TraceEventRecord]:
    statement = (
        select(TraceEventRecord)
        .where(TraceEventRecord.run_id == run_id)
        .order_by(TraceEventRecord.id)
    )
    return db.exec(statement).all()
