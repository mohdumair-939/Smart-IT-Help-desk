"""Add private ticket attachment metadata.

Revision ID: 0003_ticket_attachments
Revises: 0002_knowledge_base
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_ticket_attachments"
down_revision = "0002_knowledge_base"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "helpdesk_ticket_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("object_path", sa.String(length=768), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="uploading", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["helpdesk_tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["helpdesk_users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_path"),
    )
    op.create_index("ix_helpdesk_ticket_attachments_ticket_id", "helpdesk_ticket_attachments", ["ticket_id"])
    op.create_index("ix_helpdesk_ticket_attachments_uploaded_by_id", "helpdesk_ticket_attachments", ["uploaded_by_id"])
    op.create_index("ix_helpdesk_ticket_attachments_status", "helpdesk_ticket_attachments", ["status"])


def downgrade() -> None:
    op.drop_index("ix_helpdesk_ticket_attachments_status", table_name="helpdesk_ticket_attachments")
    op.drop_index("ix_helpdesk_ticket_attachments_uploaded_by_id", table_name="helpdesk_ticket_attachments")
    op.drop_index("ix_helpdesk_ticket_attachments_ticket_id", table_name="helpdesk_ticket_attachments")
    op.drop_table("helpdesk_ticket_attachments")
