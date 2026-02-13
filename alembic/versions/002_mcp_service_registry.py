"""MCP service registry and connection tables.

Adds two tables for managing approved MCP services (admin-managed catalog)
and per-user connection state for remote MCP services with OAuth support.

Revision ID: 002
Revises: 001
Create Date: 2025-02-12
"""

import sqlalchemy as sa

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- mcp_service_registry (FK -> organizations) --
    op.create_table(
        "mcp_service_registry",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String()),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "transport_type", sa.String(), nullable=False, server_default="stdio"
        ),
        # stdio fields
        sa.Column("command", sa.String()),
        sa.Column("args_json", sa.Text(), server_default="[]"),
        sa.Column("env_keys_json", sa.Text(), server_default="[]"),
        # streamable_http fields
        sa.Column("server_url", sa.String()),
        sa.Column("client_id", sa.String()),
        sa.Column("client_secret_encrypted", sa.Text()),
        sa.Column("default_scopes", sa.String()),
        # common
        sa.Column("icon_url", sa.String()),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "name"),
    )

    # -- mcp_connections (FK -> users, mcp_service_registry, api_key_vault) --
    op.create_table(
        "mcp_connections",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("service_id", sa.String(), nullable=False),
        sa.Column("scopes_granted", sa.String()),
        sa.Column("access_token_vault_id", sa.String()),
        sa.Column("refresh_token_vault_id", sa.String()),
        sa.Column("client_info_vault_id", sa.String()),
        sa.Column("token_expires_at", sa.DateTime()),
        sa.Column("connected_at", sa.DateTime()),
        sa.Column("last_used_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["mcp_service_registry.id"]),
        sa.ForeignKeyConstraint(["access_token_vault_id"], ["api_key_vault.id"]),
        sa.ForeignKeyConstraint(["refresh_token_vault_id"], ["api_key_vault.id"]),
        sa.ForeignKeyConstraint(["client_info_vault_id"], ["api_key_vault.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "service_id"),
    )


def downgrade() -> None:
    op.drop_table("mcp_connections")
    op.drop_table("mcp_service_registry")
