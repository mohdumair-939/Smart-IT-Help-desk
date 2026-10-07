"""Persisted AI-first troubleshooting sessions and their ticket outcomes."""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.assistant import AssistantUnavailable, grounded_answer_from_hits
from app.knowledge_base import retrieve_chunks
from app.models import AssistantSession, KnowledgeGap, Ticket, User
from app.related_tickets import find_related_tickets
from app.routers.tickets import record_activity
from app.schemas import (
    AssistantAnalysisRead,
    AssistantMessageRead,
    AssistantSessionRead,
    GroundedAnswer,
    KnowledgeGapRead,
    RelatedTicketRead,
    UserSummary,
)
from app.triage import MAX_FOLLOW_UP_QUESTIONS, IssueAnalysis, analyze_issue, retrieval_query

logger = logging.getLogger("smart_help_desk.support_assistant")
MAX_SESSION_MESSAGES = 40


def append_message(session: AssistantSession, role: str, content: str, kind: str = "message") -> None:
    messages = list(session.messages or [])
    messages.append(
        {
            "role": role,
            "content": content[:12000],
            "created_at": datetime.now(UTC).isoformat(),
            "kind": kind,
        }
    )
    session.messages = messages


def _analysis_model(session: AssistantSession) -> IssueAnalysis:
    if not session.analysis:
        raise HTTPException(status_code=409, detail="The assistant has not completed issue analysis yet.")
    return IssueAnalysis.model_validate(session.analysis)


def _gap_reason(analysis: IssueAnalysis, answer: GroundedAnswer) -> str:
    if not answer.citations:
        return "No approved knowledge article met the minimum relevance threshold for this issue."
    if answer.needs_human_support:
        return analysis.escalation_reason or "The retrieved articles were not sufficient for safe self-service."
    return "The employee reported that the cited troubleshooting did not resolve the issue."


def _record_knowledge_gap(
    db: Session,
    session: AssistantSession,
    analysis: IssueAnalysis,
    answer: GroundedAnswer,
    reason: str | None = None,
) -> KnowledgeGap:
    gap = db.scalar(select(KnowledgeGap).where(KnowledgeGap.session_id == session.id))
    if gap is None:
        gap = KnowledgeGap(
            session_id=session.id,
            requester_id=session.requester_id,
            query_text=retrieval_query(analysis),
            department=analysis.department[:120],
            category=analysis.category.value,
            priority=analysis.priority.value,
            reason=(reason or _gap_reason(analysis, answer))[:500],
            status="open",
        )
        db.add(gap)
    else:
        gap.reason = (reason or _gap_reason(analysis, answer))[:500]
        gap.department = analysis.department[:120]
        gap.category = analysis.category.value
        gap.priority = analysis.priority.value
        gap.query_text = retrieval_query(analysis)
    return gap


def process_current_turn(db: Session, session: AssistantSession, user: User) -> AssistantSessionRead:
    if len(session.messages) > MAX_SESSION_MESSAGES:
        raise HTTPException(status_code=409, detail="This troubleshooting session is full. Start a new session.")
    try:
        analysis = analyze_issue(session.messages)
    except AssistantUnavailable:
        raise
    follow_up_count = sum(1 for item in session.messages if item.get("kind") == "follow_up")
    if (
        analysis.needs_more_info
        and analysis.follow_up_question.strip()
        and not analysis.ready_for_search
        and not analysis.requires_human
        and follow_up_count < MAX_FOLLOW_UP_QUESTIONS
    ):
        session.analysis = analysis.model_dump(mode="json")
        session.answer = None
        session.retrieved_sources = []
        session.related_tickets = []
        session.status = "triage"
        append_message(session, "assistant", analysis.follow_up_question.strip(), "follow_up")
        db.commit()
        db.refresh(session)
        return session_read(session, db, user)

    if not analysis.ready_for_search and not analysis.requires_human:
        analysis = analysis.model_copy(
            update={
                "ready_for_search": True,
                "needs_more_info": False,
                "follow_up_question": "",
                "requires_human": True,
                "escalation_reason": "The issue could not be narrowed down safely with the available details.",
            }
        )

    query = retrieval_query(analysis)
    if analysis.requires_human:
        answer = GroundedAnswer(
            answer=analysis.escalation_reason or "This issue requires human IT support.",
            citations=[],
            needs_human_support=True,
        )
        related = []
    else:
        try:
            hits = retrieve_chunks(db, query, limit=5) if query else []
        except Exception as exc:
            logger.exception("Assistant retrieval failed (%s)", type(exc).__name__)
            raise AssistantUnavailable("The local knowledge search is temporarily unavailable.") from exc

        try:
            related = find_related_tickets(db, query, user) if query else []
        except Exception as exc:
            logger.warning("Related-ticket search skipped (%s)", type(exc).__name__)
            related = []

        answer = grounded_answer_from_hits(query, hits)

    session.analysis = analysis.model_dump(mode="json")
    session.answer = answer.model_dump(mode="json")
    session.retrieved_sources = [citation.model_dump(mode="json") for citation in answer.citations]
    session.related_tickets = related
    if answer.needs_human_support:
        session.status = "escalation_preview"
        reason = _gap_reason(analysis, answer)
        analysis.escalation_reason = analysis.escalation_reason or reason
        session.analysis = analysis.model_dump(mode="json")
        if not analysis.requires_human:
            _record_knowledge_gap(db, session, analysis, answer, reason)
        if answer.citations and not analysis.requires_human:
            response_text = "The cited steps did not provide a reliable self-service resolution. Review the summary below to prepare a support request."
        else:
            response_text = "This issue needs review by your IT support team. Review the detected issue and proposed routing below."
        append_message(session, "assistant", response_text)
    else:
        session.status = "solution_proposed"
        append_message(
            session,
            "assistant",
            f"{answer.answer}\n\nDid this solve your issue? You can confirm resolution or tell me what is still happening.",
        )
    db.commit()
    db.refresh(session)
    return session_read(session, db, user)


def _new_ticket_number() -> str:
    return f"HD-{datetime.now(UTC):%Y%m%d}-{uuid4().hex[:20].upper()}"


def _assign_engineer(db: Session, department: str) -> User | None:
    engineers = db.scalars(
        select(User).where(User.role == "support_engineer").order_by(User.name.asc())
    ).all()
    if not engineers:
        return None
    desired = department.casefold().strip()
    department_matches = [
        engineer
        for engineer in engineers
        if desired and (desired in engineer.department.casefold() or engineer.department.casefold() in desired)
    ]
    candidates = department_matches or engineers
    load_rows = db.execute(
        select(Ticket.assigned_engineer_id, func.count(Ticket.id))
        .where(Ticket.status.in_(("open", "in_progress", "waiting_on_requester")))
        .group_by(Ticket.assigned_engineer_id)
    ).all()
    loads = {engineer_id: count for engineer_id, count in load_rows}
    return min(candidates, key=lambda engineer: (loads.get(engineer.id, 0), engineer.name.casefold()))


def _ticket_description(session: AssistantSession, analysis: IssueAnalysis, answer: GroundedAnswer) -> str:
    lines = [
        "AI troubleshooting summary",
        f"Problem: {analysis.problem_summary}",
        f"Issue type: {analysis.issue_type or 'Not determined'}",
        f"Category: {analysis.category.value.replace('_', ' ')}",
        f"Detected department: {analysis.department}",
        f"Priority: {analysis.priority.value}",
        f"Priority reason: {analysis.priority_reason or 'Based on the reported business impact and urgency.'}",
        f"Symptoms: {'; '.join(analysis.symptoms) or 'Not provided'}",
        f"Started: {analysis.timeline or 'Not provided'}",
        f"Device: {analysis.device or 'Not provided'}",
        f"Operating system: {analysis.operating_system or 'Not provided'}",
        f"Error message: {analysis.error_message or 'Not provided'}",
        f"Affected users: {analysis.affected_users or 'Not provided'}",
        f"Business impact: {analysis.business_impact or 'Not provided'}",
        f"Likely area: {analysis.likely_area or 'Not determined'}",
        "Troubleshooting already attempted:",
    ]
    lines.extend(f"- {step}" for step in analysis.troubleshooting_attempted or ["None reported"])
    lines.extend(
        [
            f"Escalation reason: {analysis.escalation_reason or 'The employee requested human assistance.'}",
            f"Recommended next action: {analysis.recommended_action or 'Review the issue and continue diagnosis.'}",
            f"AI support answer: {answer.answer[:1800]}",
            "Knowledge sources:",
        ]
    )
    lines.extend(
        f"- {citation.title} — {citation.filename}, passage {citation.chunk_index + 1}: {citation.excerpt}"
        for citation in answer.citations
    )
    if not answer.citations:
        lines.append("- No approved source met the minimum relevance threshold.")
    lines.append("Conversation transcript:")
    lines.extend(
        f"{'Employee' if message.get('role') == 'user' else 'Assistant'}: {message.get('content', '')[:1500]}"
        for message in session.messages
    )
    return "\n".join(lines)[:12000]


def _create_ticket(
    db: Session,
    session: AssistantSession,
    analysis: IssueAnalysis,
    answer: GroundedAnswer,
    status: str,
    resolution: str | None = None,
) -> Ticket:
    engineer = _assign_engineer(db, analysis.department) if status == "open" else None
    ticket = Ticket(
        number=_new_ticket_number(),
        title=(analysis.problem_summary or "IT support request")[:180],
        description=_ticket_description(session, analysis, answer),
        category=analysis.category.value,
        priority=analysis.priority.value,
        status=status,
        department=analysis.department[:120] or "IT Support",
        requester_id=session.requester_id,
        assigned_engineer_id=engineer.id if engineer else None,
        resolution=resolution,
        resolved_at=datetime.now(UTC) if status == "resolved" else None,
    )
    db.add(ticket)
    db.flush()
    requester = db.get(User, session.requester_id)
    if requester is not None:
        action = "self_service_resolved" if status == "resolved" else "assistant_escalated"
        detail = (
            f"Self-service troubleshooting confirmed as resolved by the employee."
            if status == "resolved"
            else f"AI triage routed this request to {ticket.department}."
        )
        record_activity(db, ticket, requester, action, detail)
    return ticket


def resolve_session(
    db: Session,
    session: AssistantSession,
    user: User,
    solved: bool,
) -> AssistantSessionRead:
    if session.requester_id != user.id:
        raise HTTPException(status_code=404, detail="Troubleshooting session not found.")
    if session.status != "solution_proposed" or not session.analysis or not session.answer:
        raise HTTPException(status_code=409, detail="There is no suggested resolution to confirm.")
    analysis = _analysis_model(session)
    answer = GroundedAnswer.model_validate(session.answer)
    if solved:
        ticket = _create_ticket(
            db,
            session,
            analysis,
            answer,
            status="resolved",
            resolution=answer.answer,
        )
        session.status = "resolved"
        session.ticket_id = ticket.id
        append_message(session, "user", "The employee confirmed the suggested steps resolved the issue.")
        append_message(session, "assistant", f"Marked as resolved. A history record was saved as ticket {ticket.number}.")
    else:
        append_message(session, "user", "The suggested steps did not resolve the issue.")
        analysis.escalation_reason = "The employee confirmed that the cited self-service steps did not resolve the issue."
        session.analysis = analysis.model_dump(mode="json")
        session.answer = GroundedAnswer(
            answer="The issue is still affecting you. Review the support summary and create a ticket for an IT engineer.",
            citations=answer.citations,
            needs_human_support=True,
        ).model_dump(mode="json")
        session.status = "escalation_preview"
        _record_knowledge_gap(db, session, analysis, answer, analysis.escalation_reason)
        append_message(session, "assistant", "I’m preparing a support request with your troubleshooting history and the sources already checked.")
    db.commit()
    db.refresh(session)
    return session_read(session, db, user)


def escalate_session(db: Session, session: AssistantSession, user: User) -> AssistantSessionRead:
    if session.requester_id != user.id:
        raise HTTPException(status_code=404, detail="Troubleshooting session not found.")
    if session.status != "escalation_preview" or not session.analysis or not session.answer:
        raise HTTPException(status_code=409, detail="This session is not ready for ticket creation.")
    analysis = _analysis_model(session)
    answer = GroundedAnswer.model_validate(session.answer)
    try:
        session.related_tickets = find_related_tickets(
            db,
            retrieval_query(analysis),
            user,
            include_org_wide=True,
        )
    except Exception as exc:
        logger.warning("Cross-ticket match for escalation skipped (%s)", type(exc).__name__)
    ticket = _create_ticket(db, session, analysis, answer, status="open")
    session.ticket_id = ticket.id
    session.status = "escalated"
    assigned = db.get(User, ticket.assigned_engineer_id) if ticket.assigned_engineer_id else None
    routing = f" It is assigned to {assigned.name}." if assigned else " No support engineer is currently available, so it remains unassigned."
    append_message(session, "assistant", f"Ticket {ticket.number} was created for {ticket.department}.{routing}")
    gap = db.scalar(select(KnowledgeGap).where(KnowledgeGap.session_id == session.id))
    if gap is not None:
        gap.ticket_id = ticket.id
    db.commit()
    db.refresh(session)
    return session_read(session, db, user)


def session_read(session: AssistantSession, db: Session, user: User) -> AssistantSessionRead:
    ticket = None
    if session.ticket_id is not None:
        ticket = db.scalar(
            select(Ticket)
            .options(joinedload(Ticket.assigned_engineer))
            .where(Ticket.id == session.ticket_id)
        )
    analysis = AssistantAnalysisRead.model_validate(session.analysis) if session.analysis else None
    answer = GroundedAnswer.model_validate(session.answer) if session.answer else None
    related_data = session.related_tickets or []
    if user.role == "employee":
        related_data = [
            item
            for item in related_data
            if str(item.get("requester_id")) == str(user.id)
        ]
    return AssistantSessionRead(
        id=session.id,
        status=session.status,
        messages=[AssistantMessageRead.model_validate(message) for message in session.messages or []],
        analysis=analysis,
        answer=answer,
        related_tickets=[RelatedTicketRead.model_validate(item) for item in related_data],
        ticket_id=session.ticket_id,
        ticket_number=ticket.number if ticket else None,
        assigned_engineer=UserSummary.model_validate(ticket.assigned_engineer) if ticket and ticket.assigned_engineer else None,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def gap_read(gap: KnowledgeGap, db: Session) -> KnowledgeGapRead:
    ticket_number = None
    if gap.ticket_id is not None:
        ticket = db.get(Ticket, gap.ticket_id)
        ticket_number = ticket.number if ticket else None
    return KnowledgeGapRead(
        id=gap.id,
        session_id=gap.session_id,
        ticket_id=gap.ticket_id,
        ticket_number=ticket_number,
        query_text=gap.query_text,
        department=gap.department,
        category=gap.category,
        priority=gap.priority,
        reason=gap.reason,
        status=gap.status,
        created_at=gap.created_at,
    )


