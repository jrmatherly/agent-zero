"""pgVector document store for hybrid FAISS + pgVector architecture.

Creates the vector_documents table with HNSW index for approximate
nearest neighbor search.  This migration requires the pgvector
extension (available via ``pgvector/pgvector:pg18`` Docker image).

On SQLite (local dev), the migration is a no-op — FAISS-only mode
continues to work.  pgVector features activate only when running
against PostgreSQL.

Revision ID: 004
Revises: 003
Create Date: 2026-02-12
"""

import sqlalchemy as sa

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    """Check if we're running against PostgreSQL."""
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        # SQLite — skip pgVector setup (FAISS-only mode)
        return

    # Enable the pgVector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create table with standard columns first
    op.create_table(
        "vector_documents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("team_id", sa.String(), nullable=True),
        sa.Column("memory_subdir", sa.String(), nullable=False),
        sa.Column("area", sa.String(), server_default=sa.text("'main'")),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.String(), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add vector column via raw SQL (Alembic doesn't natively handle pgvector types)
    # 1536 = text-embedding-3-small default; re-create if model changes
    op.execute("ALTER TABLE vector_documents ADD COLUMN embedding vector(1536)")

    # HNSW index for fast approximate nearest neighbor search
    # m=16: connections per node (good balance of speed vs memory)
    # ef_construction=64: build-time quality (>95% recall)
    # vector_cosine_ops: matches FAISS DistanceStrategy.COSINE
    op.execute("""
        CREATE INDEX ix_vector_documents_embedding_hnsw
        ON vector_documents
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # Tenant isolation indexes
    op.create_index("ix_vector_documents_user_id", "vector_documents", ["user_id"])
    op.create_index("ix_vector_documents_org_id", "vector_documents", ["org_id"])
    op.create_index(
        "ix_vector_documents_memory_subdir", "vector_documents", ["memory_subdir"]
    )
    op.create_index("ix_vector_documents_area", "vector_documents", ["area"])

    # Composite index for the most common query pattern
    op.create_index(
        "ix_vector_documents_subdir_area",
        "vector_documents",
        ["memory_subdir", "area"],
    )


def downgrade() -> None:
    if not _is_postgres():
        return

    op.drop_index("ix_vector_documents_subdir_area", table_name="vector_documents")
    op.drop_index("ix_vector_documents_area", table_name="vector_documents")
    op.drop_index("ix_vector_documents_memory_subdir", table_name="vector_documents")
    op.drop_index("ix_vector_documents_org_id", table_name="vector_documents")
    op.drop_index("ix_vector_documents_user_id", table_name="vector_documents")
    op.execute("DROP INDEX IF EXISTS ix_vector_documents_embedding_hnsw")
    op.drop_table("vector_documents")
    # Don't drop the extension — other tables might use it
