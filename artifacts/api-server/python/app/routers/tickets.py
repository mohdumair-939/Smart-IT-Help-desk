from datetime import UTC, datetime
from uuid import uuid4, UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.database import get_db
from app.dependencies import visible_ticket
from app.models import Ticket, TicketActivity, TicketComment, User
from app.schemas import (
    CommentInput,
    TicketCommentRead,
    TicketInput,
    TicketCategory,
    TicketPage,
    TicketPriority,
    TicketRead,
    TicketStatus,
    TicketUpdate,
    UserRole,
)
from app.security import get_current_user

router = APIRouter(prefix="/api/v1", tags=["tickets"])
OPEN_STATUSES = ("open", "in_progress", "waiting_on_requester")


def record_activity(db: Session, ticket: Ticket, actor: User, action: str, detail: str) -> None:
    db.add(TicketActivity(ticket_id=ticket.id, actor_id=actor.id, action=action, detail=detail[:500]))


@router.get("/tickets", response_model=TicketPage)
def list_tickets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    q: str | None = None,
    status_filter: TicketStatus | None = Query(default=None, alias="status"),
    priority: TicketPriority | None = None,
    category: TicketCategory | None = None,
    department: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketPage:
    query = select(Ticket).options(joinedload(Ticket.requester), joinedload(Ticket.assigned_engineer))
    if user.role == "employee":
        query = query.where(Ticket.requester_id == user.id)
    if q and q.strip():
        search = f"%{q.strip()}%"
        query = query.where(or_(Ticket.number.ilike(search), Ticket.title.ilike(search), Ticket.description.ilike(search)))
    if status_filter:
        query = query.where(Ticket.status == status_filter.value)
    if priority:
        query = query.where(Ticket.priority == priority.value)
    if category:
        query = query.where(Ticket.category == category.value)
    if department:
        query = query.where(Ticket.department.ilike(department.strip()))
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    items = db.scalars(
        query.order_by(Ticket.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).unique().all()
    return TicketPage(items=items, page=page, page_size=page_size, total=total)


@router.post("/tickets", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: TicketInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketRead:
    ticket = Ticket(
        number=f"HD-{datetime.now(UTC):%Y%m%d}-{uuid4().hex[:20].upper()}",
        title=payload.title.strip(),
        description=payload.description.strip(),
        category=payload.category.value,
        priority=payload.priority.value,
        status="open",
        department=payload.department.strip(),
        requester_id=user.id,
    )
    db.add(ticket)
    db.flush()
    record_activity(db, ticket, user, "created", "Ticket created")
    db.commit()
    db.refresh(ticket)
    ticket = db.scalar(
        select(Ticket)
        .options(joinedload(Ticket.requester), joinedload(Ticket.assigned_engineer))
        .where(Ticket.id == ticket.id)
    )
    return TicketRead.model_validate(ticket)


@router.get("/tickets/{ticket_id}", response_model=TicketRead)
def get_ticket(ticket: Ticket = Depends(visible_ticket), db: Session = Depends(get_db)) -> TicketRead:
    loaded = db.scalar(
        select(Ticket)
        .options(joinedload(Ticket.requester), joinedload(Ticket.assigned_engineer))
        .where(Ticket.id == ticket.id)
    )
    return TicketRead.model_validate(loaded)


@router.patch("/tickets/{ticket_id}", response_model=TicketRead)
def update_ticket(
    payload: TicketUpdate,
    ticket: Ticket = Depends(visible_ticket),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketRead:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="At least one ticket field must be provided.")
    if user.role == "employee" and set(changes) - {"title", "description"}:
        raise HTTPException(status_code=403, detail="Employees may only edit their ticket title and description.")
    if user.role == "employee" and ticket.status not in OPEN_STATUSES:
        raise HTTPException(status_code=403, detail="This ticket can no longer be edited.")
    if "assigned_engineer_id" in changes and changes["assigned_engineer_id"] is not None:
        assignee = db.get(User, changes["assigned_engineer_id"])
        if assignee is None or assignee.role not in {"support_engineer", "admin"}:
            raise HTTPException(status_code=422, detail="Select an active support engineer.")
    if "status" in changes:
        next_status = changes["status"].value
        if next_status == "resolved":
            ticket.resolved_at = datetime.now(UTC)
        elif ticket.status == "resolved":
            ticket.resolved_at = None
    for key, value in changes.items():
        setattr(ticket, key, value.value if hasattr(value, "value") else value)
    ticket.updated_at = datetime.now(UTC)
    summary = ", ".join(sorted(changes.keys()))
    record_activity(db, ticket, user, "updated", f"Updated {summary}")
    db.commit()
    loaded = db.scalar(
        select(Ticket)
        .options(joinedload(Ticket.requester), joinedload(Ticket.assigned_engineer))
        .where(Ticket.id == ticket.id)
    )
    return TicketRead.model_validate(loaded)


@router.get("/tickets/{ticket_id}/comments", response_model=list[TicketCommentRead])
def list_ticket_comments(
    ticket: Ticket = Depends(visible_ticket),
    db: Session = Depends(get_db),
) -> list[TicketCommentRead]:
    comments = db.scalars(
        select(TicketComment)
        .options(joinedload(TicketComment.author))
        .where(TicketComment.ticket_id == ticket.id)
        .order_by(TicketComment.created_at.asc())
    ).unique().all()
    return [TicketCommentRead.model_validate(comment) for comment in comments]


@router.post(
    "/tickets/{ticket_id}/comments",
    response_model=TicketCommentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_ticket_comment(
    payload: CommentInput,
    ticket: Ticket = Depends(visible_ticket),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketCommentRead:
    comment = TicketComment(ticket_id=ticket.id, author_id=user.id, body=payload.body.strip())
    ticket.updated_at = datetime.now(UTC)
    db.add(comment)
    db.flush()
    record_activity(db, ticket, user, "commented", "Added a comment")
    db.commit()
    loaded_comment = db.scalar(
        select(TicketComment)
        .options(joinedload(TicketComment.author))
        .where(TicketComment.id == comment.id)
    )
    return TicketCommentRead.model_validate(loaded_comment)
