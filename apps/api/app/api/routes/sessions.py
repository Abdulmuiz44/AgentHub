from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session as DBSession

from app.api.schemas import SessionCreateRequest, SessionResponse
from app.db.session import get_session
from app.services.sessions import create_session, get_session_by_id, list_sessions

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse)
def create_session_route(payload: SessionCreateRequest, db: DBSession = Depends(get_session)):
    return create_session(db, payload.name)


@router.get("", response_model=list[SessionResponse])
def list_sessions_route(db: DBSession = Depends(get_session)):
    return list_sessions(db)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session_route(session_id: int, db: DBSession = Depends(get_session)):
    session = get_session_by_id(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
