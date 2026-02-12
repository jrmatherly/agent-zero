"""Initial auth database schema.

Creates all eight tables for the multi-tenant auth system:
organizations, teams, users, org_memberships, team_memberships,
chat_ownership, api_key_vault, and entra_group_mappings.

Revision ID: 001
Revises: None
Create Date: 2025-02-11
"""

import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- organizations (no FK dependencies) --
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("settings_json", sa.Text(), server_default="{}"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )

    # -- teams (FK -> organizations) --
    op.create_table(
        "teams",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("settings_json", sa.Text(), server_default="{}"),
        sa.Column("created_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "slug"),
    )

    # -- users (FK -> organizations) --
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("display_name", sa.String()),
        sa.Column("avatar_url", sa.String()),
        sa.Column("auth_provider", sa.String(), server_default="entra"),
        sa.Column("password_hash", sa.String()),
        sa.Column("primary_org_id", sa.String()),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1")),
        sa.Column("is_system_admin", sa.Boolean(), server_default=sa.text("0")),
        sa.Column("settings_json", sa.Text(), server_default="{}"),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("last_login_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["primary_org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    # -- org_memberships (FK -> users, organizations) --
    op.create_table(
        "org_memberships",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("user_id", "org_id"),
    )

    # -- team_memberships (FK -> users, teams) --
    op.create_table(
        "team_memberships",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("user_id", "team_id"),
    )

    # -- chat_ownership (FK -> users, teams) --
    op.create_table(
        "chat_ownership",
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("team_id", sa.String()),
        sa.Column("shared_with_json", sa.Text(), server_default="[]"),
        sa.Column("created_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("chat_id"),
    )

    # -- api_key_vault (no FK to auth tables) --
    op.create_table(
        "api_key_vault",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_type", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("key_name", sa.String(), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_type", "owner_id", "key_name"),
    )

    # -- entra_group_mappings (FK -> teams, organizations) --
    op.create_table(
        "entra_group_mappings",
        sa.Column("entra_group_id", sa.String(), nullable=False),
        sa.Column("team_id", sa.String()),
        sa.Column("org_id", sa.String()),
        sa.Column("role", sa.String(), server_default="member"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("entra_group_id"),
    )


def downgrade() -> None:
    # Drop in reverse order to respect FK dependencies
    op.drop_table("entra_group_mappings")
    op.drop_table("api_key_vault")
    op.drop_table("chat_ownership")
    op.drop_table("team_memberships")
    op.drop_table("org_memberships")
    op.drop_table("users")
    op.drop_table("teams")
    op.drop_table("organizations")
