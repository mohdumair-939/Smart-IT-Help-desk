from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Ticket, TicketActivity, User
from app.schemas import (
    ActivityRead,
    CountByLabel,
    DashboardSummary,
    EngineerWorkload,
    UserRole,
    UserSummary,
)
from app.security import get_current_user

router = APIRouter(prefix="/api/v1", tags=["dashboard"])
OPEN_STATUSES = ("open", "in_progress", "waiting_on_requester")


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardSummary:
    def count_status(status: str | tuple[str, ...]) -> int:
        query = select(func.count()).select_from(Ticket)
        if user.role == "employee":
            query = query.where(Ticket.requester_id == user.id)
        if isinstance(status, tuple):
            query = query.where(Ticket.status.in_(status))
        else:
            query = query.where(Ticket.status == status)
        return int(db.scalar(query) or 0)

    categories_query = select(Ticket.category, func.count()).select_from(Ticket)
    departments_query = select(Ticket.department, func.count()).select_from(Ticket)
    if user.role == "employee":
        categories_query = categories_query.where(Ticket.requester_id == user.id)
        departments_query = departments_query.where(Ticket.requester_id == user.id)
    categories = db.execute(categories_query.group_by(Ticket.category).order_by(func.count().desc())).all()
    departments = db.execute(departments_query.group_by(Ticket.department).order_by(func.count().desc())).all()

    workload: list[EngineerWorkload] = []
    if user.role in {"support_engineer", "admin"}:
        engineers = db.scalars(
            select(User).where(User.role == "support_engineer").order_by(User.name.asc())
        ).all()
        assignments = db.execute(
            select(Ticket.assigned_engineer_id, func.count())
            .where(Ticket.status.in_(OPEN_STATUSES))
            .group_by(Ticket.assigned_engineer_id)
        ).all()
        counts = {engineer_id: count for engineer_id, count in assignments}
        workload = [
            EngineerWorkload(engineer=engineer, open_tickets=counts.get(engineer.id, 0))
            for engineer in engineers
        ]

    urgent_query = (
        select(func.count())
        .select_from(Ticket)
        .where(Ticket.priority == "urgent", Ticket.status.in_(OPEN_STATUSES))
    )
    if user.role == "employee":
        urgent_query = urgent_query.where(Ticket.requester_id == user.id)

    return DashboardSummary(
        open_tickets=count_status(OPEN_STATUSES),
        resolved_tickets=count_status("resolved"),
        closed_tickets=count_status("closed"),
        urgent_tickets=int(db.scalar(urgent_query) or 0),
        by_category=[CountByLabel(label=str(label), count=count) for label, count in categories],
        by_department=[CountByLabel(label=str(label), count=count) for label, count in departments],
        engineer_workload=workload,
    )


@router.get("/activity", response_model=list[ActivityRead])
def recent_activity(
    limit: int = Query(default=10, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ActivityRead]:
    query = (
        select(TicketActivity)
        .join(Ticket, Ticket.id == TicketActivity.ticket_id)
        .options(joinedload(TicketActivity.actor), joinedload(TicketActivity.ticket))
        .order_by(TicketActivity.created_at.desc())
        .limit(limit)
    )
    if user.role == "employee":
        query = query.where(Ticket.requester_id == user.id)
    events = db.scalars(query).unique().all()
    return [
        ActivityRead(
            id=event.id,
            ticket_id=event.ticket_id,
            ticket_number=event.ticket.number,
            actor=event.actor,
            action=event.action,
            detail=event.detail,
            created_at=event.created_at,
        )
        for event in events
    ]


@router.get("/users", response_model=list[UserSummary])
def list_users(
    role: UserRole | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[UserSummary]:
    # Employee accounts may see support staff names for context; admins and
    # engineers can query all team members for assignment workflows.
    requested_role = role.value if role else None
    if user.role == "employee":
        requested_role = "support_engineer"
    query = select(User).order_by(User.name.asc())
    if requested_role:
        query = query.where(User.role == requested_role)
    return [UserSummary.model_validate(member) for member in db.scalars(query).all()]
