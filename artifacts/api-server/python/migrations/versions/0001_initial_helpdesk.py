"""Create users, tickets, comments, and ticket activity.

Revision ID: 0001_initial_helpdesk
Revises:
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial_helpdesk"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "helpdesk_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("department", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_helpdesk_users_email", "helpdesk_users", ["email"], unique=False)
    op.create_index("ix_helpdesk_users_role", "helpdesk_users", ["role"], unique=False)

    op.create_table(
        "helpdesk_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("department", sa.String(length=120), nullable=False),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_engineer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["assigned_engineer_id"], ["helpdesk_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requester_id"], ["helpdesk_users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("number"),
    )
    for column in ("number", "category", "priority", "status", "department", "requester_id", "assigned_engineer_id"):
        op.create_index(f"ix_helpdesk_tickets_{column}", "helpdesk_tickets", [column], unique=False)

    op.create_table(
        "helpdesk_ticket_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["helpdesk_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ticket_id"], ["helpdesk_tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_helpdesk_ticket_comments_ticket_id", "helpdesk_ticket_comments", ["ticket_id"], unique=False)
    op.create_index("ix_helpdesk_ticket_comments_author_id", "helpdesk_ticket_comments", ["author_id"], unique=False)

    op.create_table(
        "helpdesk_ticket_activity",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["helpdesk_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ticket_id"], ["helpdesk_tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_helpdesk_ticket_activity_ticket_id", "helpdesk_ticket_activity", ["ticket_id"], unique=False)
    op.create_index("ix_helpdesk_ticket_activity_actor_id", "helpdesk_ticket_activity", ["actor_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_helpdesk_ticket_activity_actor_id", table_name="helpdesk_ticket_activity")
    op.drop_index("ix_helpdesk_ticket_activity_ticket_id", table_name="helpdesk_ticket_activity")
    op.drop_table("helpdesk_ticket_activity")
    op.drop_index("ix_helpdesk_ticket_comments_author_id", table_name="helpdesk_ticket_comments")
    op.drop_index("ix_helpdesk_ticket_comments_ticket_id", table_name="helpdesk_ticket_comments")
    op.drop_table("helpdesk_ticket_comments")
    for column in ("assigned_engineer_id", "requester_id", "department", "status", "priority", "category", "number"):
        op.drop_index(f"ix_helpdesk_tickets_{column}", table_name="helpdesk_tickets")
    op.drop_table("helpdesk_tickets")
    op.drop_index("ix_helpdesk_users_role", table_name="helpdesk_users")
    op.drop_index("ix_helpdesk_users_email", table_name="helpdesk_users")
    op.drop_table("helpdesk_users")
