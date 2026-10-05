from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.database import get_db
from app.models import Ticket, User
from app.security import get_current_user


def visible_ticket(ticket_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    if user.role == "employee" and ticket.requester_id != user.id:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return ticket
