"""Add private knowledge documents and durable text chunks.

Revision ID: 0002_knowledge_base
Revises: 0001_initial_helpdesk
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_knowledge_base"
down_revision = "0001_initial_helpdesk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "helpdesk_knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("object_path", sa.String(length=768), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="uploading", nullable=False),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["helpdesk_users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_path"),
    )
    op.create_index(
        "ix_helpdesk_knowledge_documents_status", "helpdesk_knowledge_documents", ["status"], unique=False
    )
    op.create_index(
        "ix_helpdesk_knowledge_documents_uploaded_by_id",
        "helpdesk_knowledge_documents",
        ["uploaded_by_id"],
        unique=False,
    )

    op.create_table(
        "helpdesk_knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["helpdesk_knowledge_documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_helpdesk_knowledge_chunk_order"),
    )
    op.create_index(
        "ix_helpdesk_knowledge_chunks_document_id", "helpdesk_knowledge_chunks", ["document_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_helpdesk_knowledge_chunks_document_id", table_name="helpdesk_knowledge_chunks")
    op.drop_table("helpdesk_knowledge_chunks")
    op.drop_index("ix_helpdesk_knowledge_documents_uploaded_by_id", table_name="helpdesk_knowledge_documents")
    op.drop_index("ix_helpdesk_knowledge_documents_status", table_name="helpdesk_knowledge_documents")
    op.drop_table("helpdesk_knowledge_documents")
