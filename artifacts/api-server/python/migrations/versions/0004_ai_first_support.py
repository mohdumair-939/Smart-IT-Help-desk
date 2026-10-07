"""Persist AI-first support sessions and knowledge gaps.

Revision ID: 0004_ai_first_support
Revises: 0003_ticket_attachments
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_ai_first_support"
down_revision = "0003_ticket_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "helpdesk_assistant_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="triage", nullable=False),
        sa.Column("messages", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        sa.Column("analysis", sa.JSON(), nullable=True),
        sa.Column("answer", sa.JSON(), nullable=True),
        sa.Column("retrieved_sources", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        sa.Column("related_tickets", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["requester_id"], ["helpdesk_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ticket_id"], ["helpdesk_tickets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_helpdesk_assistant_sessions_requester_id", "helpdesk_assistant_sessions", ["requester_id"])
    op.create_index("ix_helpdesk_assistant_sessions_ticket_id", "helpdesk_assistant_sessions", ["ticket_id"])
    op.create_index("ix_helpdesk_assistant_sessions_status", "helpdesk_assistant_sessions", ["status"])

    op.create_table(
        "helpdesk_knowledge_gaps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("department", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["helpdesk_assistant_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requester_id"], ["helpdesk_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ticket_id"], ["helpdesk_tickets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_helpdesk_knowledge_gap_session"),
    )
    op.create_index("ix_helpdesk_knowledge_gaps_requester_id", "helpdesk_knowledge_gaps", ["requester_id"])
    op.create_index("ix_helpdesk_knowledge_gaps_ticket_id", "helpdesk_knowledge_gaps", ["ticket_id"])
    op.create_index("ix_helpdesk_knowledge_gaps_status", "helpdesk_knowledge_gaps", ["status"])


def downgrade() -> None:
    op.drop_index("ix_helpdesk_knowledge_gaps_status", table_name="helpdesk_knowledge_gaps")
    op.drop_index("ix_helpdesk_knowledge_gaps_ticket_id", table_name="helpdesk_knowledge_gaps")
    op.drop_index("ix_helpdesk_knowledge_gaps_requester_id", table_name="helpdesk_knowledge_gaps")
    op.drop_table("helpdesk_knowledge_gaps")
    op.drop_index("ix_helpdesk_assistant_sessions_status", table_name="helpdesk_assistant_sessions")
    op.drop_index("ix_helpdesk_assistant_sessions_ticket_id", table_name="helpdesk_assistant_sessions")
    op.drop_index("ix_helpdesk_assistant_sessions_requester_id", table_name="helpdesk_assistant_sessions")
    op.drop_table("helpdesk_assistant_sessions")
