import logging
from pathlib import PurePosixPath
import re
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.dependencies import visible_ticket
from app.models import Ticket, TicketActivity, TicketAttachment, User
from app.object_storage import (
    ObjectStorageError,
    attachment_object_path,
    create_download_url,
    create_upload_url,
    delete_object,
    uploaded_object_size,
)
from app.schemas import (
    TicketAttachmentDownload,
    TicketAttachmentRead,
    TicketAttachmentUploadInput,
    TicketAttachmentUploadResponse,
)
from app.security import get_current_user

logger = logging.getLogger("smart_help_desk.attachments")
router = APIRouter(prefix="/api/v1", tags=["attachments"])
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".csv", ".log"}


def _safe_filename(filename: str) -> str:
    basename = filename.replace("\\", "/").split("/")[-1].strip()
    suffix = PurePosixPath(basename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail="Attachments may be PDF, DOCX, TXT, Markdown, CSV, LOG, PNG, JPG, or JPEG files.",
        )
    stem = PurePosixPath(basename).stem
    safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-_")[:80] or "attachment"
    return f"{safe_stem}{suffix}"


def _can_manage_attachment(user: User, attachment: TicketAttachment) -> bool:
    return user.role in {"support_engineer", "admin"} or attachment.uploaded_by_id == user.id


@router.get("/tickets/{ticket_id}/attachments", response_model=list[TicketAttachmentRead])
def list_ticket_attachments(
    ticket: Ticket = Depends(visible_ticket),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TicketAttachmentRead]:
    filters = [TicketAttachment.ticket_id == ticket.id]
    if user.role == "employee":
        filters.append(
            or_(
                TicketAttachment.status == "ready",
                TicketAttachment.uploaded_by_id == user.id,
            )
        )
    attachments = db.scalars(
        select(TicketAttachment)
        .where(*filters)
        .options(selectinload(TicketAttachment.uploaded_by))
        .order_by(TicketAttachment.created_at.asc())
    ).all()
    return [TicketAttachmentRead.model_validate(attachment) for attachment in attachments]


@router.post(
    "/tickets/{ticket_id}/attachments/upload-url",
    response_model=TicketAttachmentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def request_attachment_upload(
    payload: TicketAttachmentUploadInput,
    ticket: Ticket = Depends(visible_ticket),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketAttachmentUploadResponse:
    filename = _safe_filename(payload.filename)
    attachment = TicketAttachment(
        id=uuid4(),
        ticket_id=ticket.id,
        uploaded_by_id=user.id,
        filename=filename,
        content_type=payload.content_type[:120],
        size_bytes=payload.size_bytes,
        object_path="/pending",
        status="uploading",
    )
    db.add(attachment)
    db.flush()
    attachment.object_path = attachment_object_path(ticket.id, attachment.id, filename)
    try:
        upload_url = create_upload_url(attachment.object_path)
    except ObjectStorageError as exc:
        db.rollback()
        logger.warning("App Storage attachment upload-link creation failed")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.commit()
    return TicketAttachmentUploadResponse(
        attachment_id=attachment.id,
        object_path=attachment.object_path,
        upload_url=upload_url,
    )


@router.post(
    "/tickets/{ticket_id}/attachments/{attachment_id}/complete",
    response_model=TicketAttachmentRead,
)
def complete_attachment_upload(
    attachment_id: UUID,
    ticket: Ticket = Depends(visible_ticket),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketAttachmentRead:
    attachment = db.get(TicketAttachment, attachment_id)
    if attachment is None or attachment.ticket_id != ticket.id or not _can_manage_attachment(user, attachment):
        raise HTTPException(status_code=404, detail="Attachment not found.")
    if attachment.status == "ready":
        return TicketAttachmentRead.model_validate(attachment)
    try:
        actual_size = uploaded_object_size(attachment.object_path)
    except ObjectStorageError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if actual_size != attachment.size_bytes or actual_size > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=422, detail="The uploaded file size does not match the requested upload.")
    attachment.status = "ready"
    db.add(
        TicketActivity(
            ticket_id=ticket.id,
            actor_id=user.id,
            action="attachment_added",
            detail=f"Added attachment: {attachment.filename}"[:500],
        )
    )
    db.commit()
    db.refresh(attachment)
    return TicketAttachmentRead.model_validate(attachment)


@router.get(
    "/tickets/{ticket_id}/attachments/{attachment_id}/download",
    response_model=TicketAttachmentDownload,
)
def get_attachment_download_url(
    attachment_id: UUID,
    ticket: Ticket = Depends(visible_ticket),
    db: Session = Depends(get_db),
) -> TicketAttachmentDownload:
    attachment = db.get(TicketAttachment, attachment_id)
    if attachment is None or attachment.ticket_id != ticket.id or attachment.status != "ready":
        raise HTTPException(status_code=404, detail="Attachment not found.")
    try:
        return TicketAttachmentDownload(download_url=create_download_url(attachment.object_path))
    except ObjectStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete(
    "/tickets/{ticket_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_ticket_attachment(
    attachment_id: UUID,
    ticket: Ticket = Depends(visible_ticket),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    attachment = db.get(TicketAttachment, attachment_id)
    if attachment is None or attachment.ticket_id != ticket.id or not _can_manage_attachment(user, attachment):
        raise HTTPException(status_code=404, detail="Attachment not found.")
    try:
        delete_object(attachment.object_path)
    except ObjectStorageError as exc:
        logger.warning("App Storage attachment deletion failed for attachment %s", attachment_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.add(
        TicketActivity(
            ticket_id=ticket.id,
            actor_id=user.id,
            action="attachment_removed",
            detail=f"Removed attachment: {attachment.filename}"[:500],
        )
    )
    db.delete(attachment)
    db.commit()
