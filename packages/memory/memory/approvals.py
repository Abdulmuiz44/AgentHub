from datetime import datetime

from sqlmodel import Session as DBSession, select

from .models import ApprovalRequest


def create_approval(db: DBSession, *, run_id: int, step_id: str | None, reason: str) -> ApprovalRequest:
    approval = ApprovalRequest(run_id=run_id, step_id=step_id, reason=reason)
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval


def get_approval(db: DBSession, approval_id: int) -> ApprovalRequest | None:
    return db.get(ApprovalRequest, approval_id)


def get_pending_approval_for_step(db: DBSession, run_id: int, step_id: str | None) -> ApprovalRequest | None:
    statement = (
        select(ApprovalRequest)
        .where(ApprovalRequest.run_id == run_id)
        .where(ApprovalRequest.step_id == step_id)
        .order_by(ApprovalRequest.id.desc())
    )
    approvals = db.exec(statement).all()
    for approval in approvals:
        if approval.status == "pending":
            return approval
    return approvals[0] if approvals else None


def get_latest_pending_approval(db: DBSession, run_id: int) -> ApprovalRequest | None:
    statement = (
        select(ApprovalRequest)
        .where(ApprovalRequest.run_id == run_id)
        .where(ApprovalRequest.status == "pending")
        .order_by(ApprovalRequest.id.desc())
    )
    return db.exec(statement).first()


def update_approval(
    db: DBSession,
    approval: ApprovalRequest,
    *,
    status: str,
    resolution_summary: str | None = None,
) -> ApprovalRequest:
    approval.status = status
    approval.resolution_summary = resolution_summary
    approval.updated_at = datetime.utcnow()
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval
