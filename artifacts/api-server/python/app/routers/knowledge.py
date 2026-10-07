import logging
from pathlib import PurePosixPath
import re
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assistant import AssistantUnavailable, grounded_answer
from app.database import SessionLocal, get_db
from app.dependencies import visible_ticket
from app.knowledge_base import ingest_document, remove_document_chunks
from app.models import KnowledgeChunk, KnowledgeDocument, Ticket, User
from app.object_storage import ObjectStorageError, create_upload_url, delete_object, object_path_for
from app.schemas import (
    GroundedAnswer,
    KnowledgeDocumentRead,
    KnowledgeResolutionDraftRead,
    KnowledgeSearchInput,
    KnowledgeUploadInput,
    KnowledgeUploadResponse,
)
from app.security import get_current_user, require_admin

logger = logging.getLogger("smart_help_desk.knowledge_api")
router = APIRouter(prefix="/api/v1", tags=["knowledge"])
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


@router.get(
    "/knowledge/tickets/{ticket_id}/resolution-draft",
    response_model=KnowledgeResolutionDraftRead,
)
def resolution_article_draft(
    ticket_id: UUID,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> KnowledgeResolutionDraftRead:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    if ticket.status not in {"resolved", "closed"} or not ticket.resolution or len(ticket.resolution.strip()) < 20:
        raise HTTPException(status_code=409, detail="Resolve the ticket with a useful resolution before drafting an article.")
    safe_title = re.sub(r"[\r\n#]+", " ", ticket.title).strip()[:160] or "Support resolution"
    markdown = (
        f"# {safe_title}\n\n"
        f"**Category:** {ticket.category.replace('_', ' ')}  \n"
        f"**Support department:** {ticket.department}\n\n"
        "## Resolution\n\n"
        f"{ticket.resolution.strip()[:8000]}\n\n"
        "> Review this draft for organization-specific details, credentials, and personal information before publishing.\n"
    )
    return KnowledgeResolutionDraftRead(
        ticket_id=ticket.id,
        ticket_number=ticket.number,
        title=f"{safe_title} — resolution guide"[:180],
        filename=f"{ticket.number.lower()}-resolution.md",
        content_type="text/markdown",
        markdown=markdown,
    )


def _clean_filename(value: str) -> str:
    name = value.replace("\\", "/").split("/")[-1].strip()
    suffix = PurePosixPath(name).suffix.lower()
    stem = PurePosixPath(name).stem
    safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-_")[:80] or "document"
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail="Upload a PDF, DOCX, TXT, or Markdown document.")
    return f"{safe_stem}{suffix}"


@router.post(
    "/knowledge/documents/upload-url",
    response_model=KnowledgeUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def request_knowledge_upload(
    payload: KnowledgeUploadInput,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> KnowledgeUploadResponse:
    filename = _clean_filename(payload.filename)
    if payload.size_bytes > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Documents must be 15 MB or smaller.")
    document = KnowledgeDocument(
        title=payload.title.strip(),
        filename=filename,
        content_type=payload.content_type[:120],
        object_path="/pending",
        size_bytes=payload.size_bytes,
        status="uploading",
        uploaded_by_id=admin.id,
    )
    db.add(document)
    db.flush()
    document.object_path = object_path_for(document.id, filename)
    try:
        upload_url = create_upload_url(document.object_path)
    except ObjectStorageError as exc:
        db.rollback()
        logger.warning("App Storage upload-link creation failed")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.commit()
    return KnowledgeUploadResponse(
        document_id=document.id,
        object_path=document.object_path,
        upload_url=upload_url,
    )


@router.get("/knowledge/documents", response_model=list[KnowledgeDocumentRead])
def list_knowledge_documents(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[KnowledgeDocumentRead]:
    documents = db.scalars(
        select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
    ).all()
    return [KnowledgeDocumentRead.model_validate(document) for document in documents]


@router.post(
    "/knowledge/documents/{document_id}/ingest",
    response_model=KnowledgeDocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def ingest_knowledge_document(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> KnowledgeDocumentRead:
    document = db.get(KnowledgeDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found.")
    if document.status in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="This document is already being indexed.")
    if document.status == "ready":
        return KnowledgeDocumentRead.model_validate(document)
    document.status = "queued"
    document.error_message = None
    db.commit()
    db.refresh(document)
    background_tasks.add_task(ingest_document, document.id, SessionLocal)
    return KnowledgeDocumentRead.model_validate(document)


@router.delete("/knowledge/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_document(
    document_id: UUID,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    document = db.get(KnowledgeDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found.")
    chunk_ids = db.scalars(
        select(KnowledgeChunk.id).where(KnowledgeChunk.document_id == document_id)
    ).all()
    try:
        delete_object(document.object_path)
    except ObjectStorageError as exc:
        logger.warning("App Storage document deletion failed for document %s", document_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.delete(document)
    db.commit()
    remove_document_chunks(chunk_ids)


@router.post("/knowledge/search", response_model=GroundedAnswer)
def search_knowledge(
    payload: KnowledgeSearchInput,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroundedAnswer:
    try:
        return grounded_answer(db, payload.query.strip())
    except AssistantUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/tickets/{ticket_id}/ai-resolution", response_model=GroundedAnswer)
def ticket_resolution_help(
    ticket: Ticket = Depends(visible_ticket),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroundedAnswer:
    question = f"{ticket.title}\n{ticket.category}\n{ticket.description}"[:2000]
    context = (
        f"Category: {ticket.category}\n"
        f"Priority: {ticket.priority}\n"
        f"Ticket description:\n{ticket.description[:5000]}"
    )
    try:
        return grounded_answer(db, question, ticket_context=context)
    except AssistantUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
