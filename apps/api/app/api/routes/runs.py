import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session as SQLSession, Session as DBSession

from app.api.schemas import ApprovalResolveResponse, RunCreateRequest, RunCreateResponse, RunResponse, TraceResponse
from app.db.session import engine, get_session
from app.services.runs import cancel_run, create_run, get_run, get_run_response, list_trace, resolve_approval
from core.contracts import AgentRequest, ApprovalStatus, ExecutionMode, RunStatus

router = APIRouter(tags=["runs"])


def _worker(request: Request):
    return request.app.state.run_worker


@router.post("/runs", response_model=RunCreateResponse)
def create_run_route(payload: RunCreateRequest, request: Request, db: DBSession = Depends(get_session)):
    agent_request = AgentRequest(
        task=payload.task,
        session_id=payload.session_id,
        provider=payload.provider,
        model=payload.model,
        enabled_skills=payload.enabled_skills,
        execution_mode=ExecutionMode(payload.execution_mode),
    )
    run, _session, events = create_run(db, agent_request)
    _worker(request).enqueue(run.id)
    run_payload = get_run_response(db, run.id)
    return {
        "run": run_payload,
        "trace_events": events,
    }


@router.get("/runs/{run_id}", response_model=RunResponse)
def get_run_route(run_id: int, db: DBSession = Depends(get_session)):
    run = get_run_response(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/runs/{run_id}/trace", response_model=list[TraceResponse])
def get_trace_route(run_id: int, db: DBSession = Depends(get_session)):
    run = get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return list_trace(db, run_id)


@router.post("/runs/{run_id}/cancel", response_model=RunResponse)
def cancel_run_route(run_id: int, request: Request, db: DBSession = Depends(get_session)):
    run = cancel_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run["status"] in {RunStatus.RUNNING.value, RunStatus.QUEUED.value, RunStatus.WAITING_FOR_APPROVAL.value}:
        _worker(request).enqueue(run_id)
    return run


@router.post("/runs/{run_id}/approvals/{approval_id}/approve", response_model=ApprovalResolveResponse)
def approve_run_step(run_id: int, approval_id: int, request: Request, db: DBSession = Depends(get_session)):
    resolved = resolve_approval(db, run_id, approval_id, status=ApprovalStatus.APPROVED, summary="Approval granted.")
    if resolved is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    run_payload, approval_payload = resolved
    _worker(request).enqueue(run_id)
    return {"run": run_payload, "approval": approval_payload}


@router.post("/runs/{run_id}/approvals/{approval_id}/deny", response_model=ApprovalResolveResponse)
def deny_run_step(run_id: int, approval_id: int, request: Request, db: DBSession = Depends(get_session)):
    resolved = resolve_approval(db, run_id, approval_id, status=ApprovalStatus.DENIED, summary="Approval denied.")
    if resolved is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    run_payload, approval_payload = resolved
    _worker(request).enqueue(run_id)
    return {"run": run_payload, "approval": approval_payload}


@router.get("/runs/{run_id}/stream")
async def run_stream(run_id: int, request: Request):
    with SQLSession(engine) as db:
        existing_run = get_run(db, run_id)
        if existing_run is None:
            raise HTTPException(status_code=404, detail="Run not found")

    async def event_generator():
        last_trace_id = 0
        last_status = None
        while True:
            if await request.is_disconnected():
                break
            with SQLSession(engine) as db:
                current_run = get_run_response(db, run_id)
                if current_run is None:
                    break
                trace_items = list_trace(db, run_id, after_id=last_trace_id)
            for item in trace_items:
                last_trace_id = max(last_trace_id, item.id)
                payload = {"id": item.id, "run_id": item.run_id, "event_type": item.event_type, "payload": item.payload, "created_at": item.created_at.isoformat()}
                yield f"data: {json.dumps({'type': 'trace', 'data': payload})}\n\n"
            if current_run["status"] != last_status:
                last_status = current_run["status"]
                yield f"data: {json.dumps({'type': 'run', 'data': current_run}, default=str)}\n\n"
            if current_run["status"] in {RunStatus.COMPLETED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value}:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

