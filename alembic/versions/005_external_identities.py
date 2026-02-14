"""Add external_identities table for platform user linking.

Revision ID: 005
Revises: 004
Create Date: 2026-02-14
"""

import sqlalchemy as sa

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_identities",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("external_user_id", sa.String(), nullable=False),
        sa.Column("external_display_name", sa.String()),
        sa.Column("external_team_id", sa.String()),
        sa.Column("access_token_vault_id", sa.String()),
        sa.Column("refresh_token_vault_id", sa.String()),
        sa.Column("token_expires_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("last_used_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["access_token_vault_id"], ["api_key_vault.id"]),
        sa.ForeignKeyConstraint(["refresh_token_vault_id"], ["api_key_vault.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", "external_user_id"),
    )
    op.create_index(
        "ix_external_identities_user_id",
        "external_identities",
        ["user_id"],
    )
    op.create_index(
        "ix_external_identities_platform_user",
        "external_identities",
        ["platform", "external_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_external_identities_platform_user")
    op.drop_index("ix_external_identities_user_id")
    op.drop_table("external_identities")
