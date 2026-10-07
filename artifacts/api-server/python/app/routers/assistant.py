from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import visible_ticket
from app.models import AssistantSession, KnowledgeGap, Ticket, User
from app.schemas import (
    AssistantMessageInput,
    AssistantResolveInput,
    AssistantSessionRead,
    KnowledgeGapRead,
    TicketRead,
)
from app.security import get_current_user, require_admin
from app.support_assistant import (
    append_message,
    escalate_session,
    gap_read,
    process_current_turn,
    resolve_session,
    session_read,
)

router = APIRouter(prefix="/api/v1", tags=["assistant"])


def _owned_session(session_id: UUID, user: User, db: Session) -> AssistantSession:
    session = db.get(AssistantSession, session_id)
    if session is None or session.requester_id != user.id:
        raise HTTPException(status_code=404, detail="Troubleshooting session not found.")
    return session


@router.post("/assistant/sessions", response_model=AssistantSessionRead, status_code=status.HTTP_201_CREATED)
def create_assistant_session(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssistantSessionRead:
    session = AssistantSession(requester_id=user.id, status="triage", messages=[])
    db.add(session)
    db.commit()
    db.refresh(session)
    return session_read(session, db, user)


@router.get("/assistant/sessions", response_model=list[AssistantSessionRead])
def list_assistant_sessions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AssistantSessionRead]:
    statement = select(AssistantSession).order_by(AssistantSession.updated_at.desc()).limit(30)
    if user.role == "employee":
        statement = statement.where(AssistantSession.requester_id == user.id)
    elif user.role == "support_engineer":
        statement = statement.join(Ticket, AssistantSession.ticket_id == Ticket.id).where(
            Ticket.assigned_engineer_id == user.id
        )
    sessions = db.scalars(statement).all()
    return [session_read(item, db, user) for item in sessions]


@router.get("/assistant/sessions/{session_id}", response_model=AssistantSessionRead)
def get_assistant_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssistantSessionRead:
    session = _owned_session(session_id, user, db)
    return session_read(session, db, user)


@router.post("/assistant/sessions/{session_id}/messages", response_model=AssistantSessionRead)
def send_assistant_message(
    session_id: UUID,
    payload: AssistantMessageInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssistantSessionRead:
    session = _owned_session(session_id, user, db)
    if session.status in {"resolved", "escalated"}:
        raise HTTPException(status_code=409, detail="This support session is already complete.")
    if len(session.messages or []) >= 40:
        raise HTTPException(status_code=409, detail="This troubleshooting session is full. Start a new session.")
    append_message(session, "user", payload.message.strip())
    session.status = "triage"
    session.answer = None
    db.commit()
    return process_current_turn(db, session, user)


@router.post("/assistant/sessions/{session_id}/retry", response_model=AssistantSessionRead)
def retry_assistant_turn(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssistantSessionRead:
    session = _owned_session(session_id, user, db)
    if not session.messages or session.messages[-1].get("role") != "user":
        raise HTTPException(status_code=409, detail="There is no failed assistant response to retry.")
    return process_current_turn(db, session, user)


@router.post("/assistant/sessions/{session_id}/resolution", response_model=AssistantSessionRead)
def confirm_assistant_resolution(
    session_id: UUID,
    payload: AssistantResolveInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssistantSessionRead:
    session = _owned_session(session_id, user, db)
    return resolve_session(db, session, user, payload.solved)


@router.post("/assistant/sessions/{session_id}/escalate", response_model=AssistantSessionRead)
def create_escalated_ticket(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssistantSessionRead:
    session = _owned_session(session_id, user, db)
    return escalate_session(db, session, user)


@router.get("/tickets/{ticket_id}/assistant-context", response_model=AssistantSessionRead | None)
def get_ticket_assistant_context(
    ticket: Ticket = Depends(visible_ticket),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssistantSessionRead | None:
    session = db.scalar(
        select(AssistantSession)
        .options(joinedload(AssistantSession.requester))
        .where(AssistantSession.ticket_id == ticket.id)
    )
    if session is None:
        return None
    return session_read(session, db, user)


@router.get("/assistant/knowledge-gaps", response_model=list[KnowledgeGapRead])
def list_knowledge_gaps(
    gap_status: str | None = Query(default="open", alias="status", pattern="^(open|closed|all)$"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[KnowledgeGapRead]:
    statement = select(KnowledgeGap).order_by(KnowledgeGap.created_at.desc()).limit(200)
    if gap_status and gap_status != "all":
        statement = statement.where(KnowledgeGap.status == gap_status)
    gaps = db.scalars(statement).all()
    return [gap_read(gap, db) for gap in gaps]


@router.post("/assistant/knowledge-gaps/{gap_id}/close", response_model=KnowledgeGapRead)
def close_knowledge_gap(
    gap_id: UUID,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> KnowledgeGapRead:
    gap = db.get(KnowledgeGap, gap_id)
    if gap is None:
        raise HTTPException(status_code=404, detail="Knowledge gap not found.")
    gap.status = "closed"
    db.commit()
    db.refresh(gap)
    return gap_read(gap, db)
