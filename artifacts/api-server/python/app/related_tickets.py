"""Private, local-embedding similarity search over prior ticket text."""

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge_base import embed_for_similarity, embed_query_for_similarity
from app.models import Ticket, User

MAX_TICKET_CANDIDATES = 180
MIN_TICKET_RELEVANCE = 0.52


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def find_related_tickets(
    db: Session,
    query: str,
    user: User,
    limit: int = 3,
    include_org_wide: bool = False,
) -> list[dict[str, object]]:
    statement = select(Ticket).order_by(Ticket.updated_at.desc()).limit(MAX_TICKET_CANDIDATES)
    if user.role == "employee" and not include_org_wide:
        statement = statement.where(Ticket.requester_id == user.id)
    candidates = db.scalars(statement).all()
    if not candidates or not query.strip():
        return []

    candidate_texts = [
        "\n".join(
            value
            for value in (
                ticket.title,
                ticket.category.replace("_", " "),
                ticket.description[:1400],
                ticket.resolution or "",
            )
            if value
        )
        for ticket in candidates
    ]
    query_vector = embed_query_for_similarity(query)
    vectors = embed_for_similarity(candidate_texts)
    results: list[dict[str, object]] = []
    for ticket, vector in zip(candidates, vectors, strict=True):
        score = _cosine_similarity(query_vector, vector)
        if score >= MIN_TICKET_RELEVANCE:
            results.append(
                {
                    "id": str(ticket.id),
                    "number": ticket.number,
                    "title": ticket.title,
                    "status": ticket.status,
                    "resolution": (ticket.resolution or "")[:800] or None,
                    "relevance": round(max(0.0, min(1.0, score)), 3),
                    "requester_id": str(ticket.requester_id),
                }
            )
    return sorted(results, key=lambda item: float(item["relevance"]), reverse=True)[:limit]
