from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session as DBSession

from app.api.schemas import RunCreateRequest, RunCreateResponse, RunResponse, TraceResponse
from app.db.session import get_session
from app.services.runs import create_run, get_run, list_trace
from core.contracts import AgentRequest

router = APIRouter(tags=["runs"])


@router.post("/runs", response_model=RunCreateResponse)
def create_run_route(payload: RunCreateRequest, db: DBSession = Depends(get_session)):
    request = AgentRequest(
        task=payload.task,
        session_id=payload.session_id,
        provider=payload.provider,
        model=payload.model,
        enabled_skills=payload.enabled_skills,
    )
    run, _session, events, metadata = create_run(db, request, execute_now=payload.execute_now)
    return {
        "run": run,
        "trace_events": events,
        "execution_metadata": metadata,
    }


@router.get("/runs/{run_id}", response_model=RunResponse)
def get_run_route(run_id: int, db: DBSession = Depends(get_session)):
    run = get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/runs/{run_id}/trace", response_model=list[TraceResponse])
def get_trace_route(run_id: int, db: DBSession = Depends(get_session)):
    run = get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return list_trace(db, run_id)
