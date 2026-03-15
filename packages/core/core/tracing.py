from .contracts import EventType, TraceEvent


class TraceCollector:
    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    def record(self, event: TraceEvent) -> None:
        self._events.append(event)

    def record_simple(self, run_id: int, event_type: EventType, payload: dict | None = None) -> None:
        self.record(TraceEvent(run_id=run_id, event_type=event_type, payload=payload or {}))

    def events(self) -> list[TraceEvent]:
        return list(self._events)
