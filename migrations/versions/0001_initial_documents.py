"""Initial creation of documents table

Revision ID: 0001_initial_documents
Revises:
Create Date: 2026-10-19 17:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_documents"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("checksum_sha256", name="uq_documents_checksum_sha256"),
    )
    op.create_index(
        op.f("ix_documents_checksum_sha256"), "documents", ["checksum_sha256"], unique=True
    )
    op.create_index(op.f("ix_documents_created_at"), "documents", ["created_at"], unique=False)
    op.create_index("ix_documents_created_at_id", "documents", ["created_at", "id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_documents_created_at_id", table_name="documents")
    op.drop_index(op.f("ix_documents_created_at"), table_name="documents")
    op.drop_index(op.f("ix_documents_checksum_sha256"), table_name="documents")
    op.drop_table("documents")
