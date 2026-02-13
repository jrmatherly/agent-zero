"""SQLAlchemy ORM models and CRUD operations for the multi-tenant auth database.

Defines ten models covering organizations, teams, users, memberships,
chat ownership, API key vaulting, EntraID group mappings, MCP service
registry, and MCP connections.  All models inherit from the shared
``Base`` declared in :mod:`python.helpers.auth_db`.
"""

import uuid
from datetime import datetime, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Session, relationship

from python.helpers import vault_crypto
from python.helpers.auth_db import Base

# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String, primary_key=True)  # UUID
    name = Column(String, nullable=False, unique=True)
    slug = Column(String, nullable=False, unique=True)  # URL-safe
    settings_json = Column(Text, default="{}")  # Org setting overrides
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    teams = relationship("Team", back_populates="organization")
    members = relationship("OrgMembership", back_populates="organization")


class Team(Base):
    __tablename__ = "teams"

    id = Column(String, primary_key=True)  # UUID
    org_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    settings_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("org_id", "slug"),)

    organization = relationship("Organization", back_populates="teams")
    members = relationship("TeamMembership", back_populates="team")


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)  # EntraID 'oid' claim or UUID for local
    email = Column(String, nullable=False, unique=True)
    display_name = Column(String)
    avatar_url = Column(String)
    auth_provider = Column(String, default="entra")  # "entra" or "local"
    password_hash = Column(String)  # argon2 hash, only for local accounts
    primary_org_id = Column(String, ForeignKey("organizations.id"))
    is_active = Column(Boolean, default=True)
    is_system_admin = Column(Boolean, default=False)
    settings_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login_at = Column(DateTime)

    org_memberships = relationship("OrgMembership", back_populates="user")
    team_memberships = relationship("TeamMembership", back_populates="user")


class OrgMembership(Base):
    __tablename__ = "org_memberships"

    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    org_id = Column(String, ForeignKey("organizations.id"), primary_key=True)
    role = Column(String, nullable=False, default="member")  # owner, admin, member
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="org_memberships")
    organization = relationship("Organization", back_populates="members")


class TeamMembership(Base):
    __tablename__ = "team_memberships"

    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    team_id = Column(String, ForeignKey("teams.id"), primary_key=True)
    role = Column(String, nullable=False, default="member")  # lead, member, viewer
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="team_memberships")
    team = relationship("Team", back_populates="members")


class ChatOwnership(Base):
    __tablename__ = "chat_ownership"

    chat_id = Column(String, primary_key=True)  # AgentContext.id
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    team_id = Column(String, ForeignKey("teams.id"))
    shared_with_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ApiKeyVault(Base):
    __tablename__ = "api_key_vault"

    id = Column(String, primary_key=True)  # UUID
    owner_type = Column(String, nullable=False)  # "user", "team", "org", "system"
    owner_id = Column(String, nullable=False)
    key_name = Column(String, nullable=False)  # e.g., "API_KEY_OPENAI"
    encrypted_value = Column(Text, nullable=False)  # AES-256-GCM via vault_crypto
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("owner_type", "owner_id", "key_name"),)


class EntraGroupMapping(Base):
    __tablename__ = "entra_group_mappings"

    entra_group_id = Column(String, primary_key=True)  # EntraID Group Object ID (GUID)
    team_id = Column(String, ForeignKey("teams.id"))
    org_id = Column(String, ForeignKey("organizations.id"))
    role = Column(String, default="member")  # Role to assign on sync


class McpServiceRegistry(Base):
    """Admin-managed catalog of approved MCP services."""

    __tablename__ = "mcp_service_registry"

    id = Column(String, primary_key=True)
    org_id = Column(String, ForeignKey("organizations.id"))  # NULL = system-wide
    name = Column(String, nullable=False)
    transport_type = Column(
        String, nullable=False, default="stdio"
    )  # "stdio" or "streamable_http"
    # stdio fields
    command = Column(String)
    args_json = Column(Text, default="[]")
    env_keys_json = Column(Text, default="[]")
    # streamable_http fields
    server_url = Column(String)
    client_id = Column(String)
    client_secret_encrypted = Column(Text)
    default_scopes = Column(String)
    # common
    icon_url = Column(String)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("org_id", "name"),)

    organization = relationship("Organization")
    connections = relationship("McpConnection", back_populates="service")


class McpConnection(Base):
    """Per-user connection state for remote MCP services."""

    __tablename__ = "mcp_connections"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    service_id = Column(String, ForeignKey("mcp_service_registry.id"), nullable=False)
    scopes_granted = Column(String)
    access_token_vault_id = Column(String, ForeignKey("api_key_vault.id"))
    refresh_token_vault_id = Column(String, ForeignKey("api_key_vault.id"))
    client_info_vault_id = Column(String, ForeignKey("api_key_vault.id"))
    token_expires_at = Column(DateTime)
    connected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime)

    __table_args__ = (UniqueConstraint("user_id", "service_id"),)

    user = relationship("User")
    service = relationship("McpServiceRegistry", back_populates="connections")


class VectorDocument(Base):
    """Durable vector storage backed by pgVector.

    Used as the shared source of truth across Kubernetes pods.
    FAISS remains the in-memory hot cache for active sessions.
    """

    __tablename__ = "vector_documents"

    id = Column(String, primary_key=True)  # matches FAISS doc ID
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    org_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    team_id = Column(String, ForeignKey("teams.id"))
    memory_subdir = Column(String, nullable=False)  # tenant-scoped path
    area = Column(String, default="main")  # main / fragments / solutions
    content = Column(Text, nullable=False)  # document page_content
    metadata_json = Column(Text)  # serialized doc metadata (minus embedding)
    embedding = Column(Vector(1536))  # dimension configurable via migration
    embedding_model = Column(String)  # e.g. "openai/text-embedding-3-small"
    embedding_dimensions = Column(Integer)  # actual vector length
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        # Tenant isolation + subdir lookup
        # HNSW index created in migration (not expressible as SA Index)
    )

    user = relationship("User")
    organization = relationship("Organization")


# ---------------------------------------------------------------------------
# Password utilities (argon2)
# ---------------------------------------------------------------------------

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _ph.hash(password)


def verify_password(user: User, password: str) -> bool:
    """Verify a plaintext password against a user's stored hash."""
    if not user.password_hash:
        return False
    try:
        return _ph.verify(user.password_hash, password)
    except VerifyMismatchError:
        return False


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------


def get_user_by_id(db: Session, user_id: str) -> User | None:
    """Look up a user by primary key."""
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_email(db: Session, email: str) -> User | None:
    """Look up a user by email address."""
    return db.query(User).filter(User.email == email).first()


def upsert_user(db: Session, userinfo: dict) -> User:
    """JIT provisioning -- create or update a user from OIDC claims."""
    user = get_user_by_id(db, userinfo["sub"])
    now = datetime.now(timezone.utc)
    if user is None:
        user = User(
            id=userinfo["sub"],
            email=userinfo["email"],
            display_name=userinfo.get("name"),
            auth_provider=userinfo.get("auth_method", "entra"),
            last_login_at=now,
        )
        db.add(user)
    else:
        # Update mutable fields on each login
        user.email = userinfo["email"]
        user.display_name = userinfo.get("name") or user.display_name
        user.last_login_at = now
    return user


def create_local_user(
    db: Session,
    email: str,
    password: str,
    display_name: str | None = None,
    *,
    is_system_admin: bool = False,
) -> User:
    """Create a local (non-SSO) user account."""
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        display_name=display_name or email.split("@")[0],
        auth_provider="local",
        password_hash=hash_password(password),
        is_system_admin=is_system_admin,
    )
    db.add(user)
    return user


# ---------------------------------------------------------------------------
# Group sync
# ---------------------------------------------------------------------------


def sync_group_memberships(db: Session, user: User, group_ids: list[str]) -> None:
    """Sync EntraID group memberships to local team/org memberships.

    For each group ID in the claim, look up the EntraGroupMapping
    and create/update OrgMembership and TeamMembership records.
    Remove memberships for groups the user is no longer in.
    """
    current_mappings = (
        db.query(EntraGroupMapping)
        .filter(EntraGroupMapping.entra_group_id.in_(group_ids))
        .all()
    )

    # Collect desired org_ids and team_ids from mappings
    desired_org_ids: set[str] = set()
    desired_team_ids: set[str] = set()
    # Map org_id/team_id -> role from the mapping for upsert
    org_role_map: dict[str, str] = {}
    team_role_map: dict[str, str] = {}

    for mapping in current_mappings:
        if mapping.org_id:
            desired_org_ids.add(mapping.org_id)
            org_role_map[mapping.org_id] = mapping.role
        if mapping.team_id:
            desired_team_ids.add(mapping.team_id)
            team_role_map[mapping.team_id] = mapping.role

    # Batch-fetch existing org memberships for this user (single query)
    existing_org_mems: dict[str, OrgMembership] = {}
    if desired_org_ids:
        for mem in (
            db.query(OrgMembership)
            .filter(
                OrgMembership.user_id == user.id,
                OrgMembership.org_id.in_(desired_org_ids),
            )
            .all()
        ):
            existing_org_mems[mem.org_id] = mem

    # Upsert org memberships
    for org_id in desired_org_ids:
        role = org_role_map[org_id]
        if org_id in existing_org_mems:
            existing_org_mems[org_id].role = role
        else:
            db.add(OrgMembership(user_id=user.id, org_id=org_id, role=role))

    # Batch-fetch existing team memberships for this user (single query)
    existing_team_mems: dict[str, TeamMembership] = {}
    if desired_team_ids:
        for mem in (
            db.query(TeamMembership)
            .filter(
                TeamMembership.user_id == user.id,
                TeamMembership.team_id.in_(desired_team_ids),
            )
            .all()
        ):
            existing_team_mems[mem.team_id] = mem

    # Upsert team memberships
    for team_id in desired_team_ids:
        role = team_role_map[team_id]
        if team_id in existing_team_mems:
            existing_team_mems[team_id].role = role
        else:
            db.add(TeamMembership(user_id=user.id, team_id=team_id, role=role))

    # Remove team memberships for groups user is no longer in
    # (only remove those that were originally created via group sync)
    # Single query to get all mapped team IDs
    all_mapped_team_ids = {
        m.team_id
        for m in db.query(EntraGroupMapping.team_id)
        .filter(EntraGroupMapping.team_id != None)  # noqa: E711
        .all()
    }
    if all_mapped_team_ids:
        current_team_mems_list = (
            db.query(TeamMembership)
            .filter(
                TeamMembership.user_id == user.id,
                TeamMembership.team_id.in_(all_mapped_team_ids),
            )
            .all()
        )
        for mem in current_team_mems_list:
            if mem.team_id not in desired_team_ids:
                db.delete(mem)


# ---------------------------------------------------------------------------
# Org / Team CRUD (basic)
# ---------------------------------------------------------------------------


def create_organization(db: Session, name: str, slug: str) -> Organization:
    """Create a new organization."""
    org = Organization(id=str(uuid.uuid4()), name=name, slug=slug)
    db.add(org)
    return org


def create_team(db: Session, org_id: str, name: str, slug: str) -> Team:
    """Create a new team within an organization."""
    team = Team(id=str(uuid.uuid4()), org_id=org_id, name=name, slug=slug)
    db.add(team)
    return team


# ---------------------------------------------------------------------------
# Organization CRUD (extended)
# ---------------------------------------------------------------------------


def list_organizations(db: Session, *, is_active: bool = True) -> list[Organization]:
    """List organizations, optionally filtering by active status."""
    return db.query(Organization).filter(Organization.is_active == is_active).all()


def get_organization_by_id(db: Session, org_id: str) -> Organization | None:
    """Look up an organization by primary key."""
    return db.query(Organization).filter(Organization.id == org_id).first()


def update_organization(db: Session, org_id: str, **kwargs) -> Organization:
    """Update mutable fields on an organization."""
    org = db.query(Organization).filter(Organization.id == org_id).one()
    for key, value in kwargs.items():
        if hasattr(org, key) and key not in ("id", "created_at"):
            setattr(org, key, value)
    return org


def deactivate_organization(db: Session, org_id: str) -> None:
    """Soft-delete an organization by setting is_active=False."""
    org = db.query(Organization).filter(Organization.id == org_id).one()
    org.is_active = False


# ---------------------------------------------------------------------------
# Team CRUD (extended)
# ---------------------------------------------------------------------------


def list_teams(db: Session, org_id: str) -> list[Team]:
    """List all teams within an organization."""
    return db.query(Team).filter(Team.org_id == org_id).all()


def get_team_by_id(db: Session, team_id: str) -> Team | None:
    """Look up a team by primary key."""
    return db.query(Team).filter(Team.id == team_id).first()


def update_team(db: Session, team_id: str, **kwargs) -> Team:
    """Update mutable fields on a team."""
    team = db.query(Team).filter(Team.id == team_id).one()
    for key, value in kwargs.items():
        if hasattr(team, key) and key not in ("id", "org_id", "created_at"):
            setattr(team, key, value)
    return team


def delete_team(db: Session, team_id: str) -> None:
    """Delete a team (hard delete — remove memberships first)."""
    db.query(TeamMembership).filter(TeamMembership.team_id == team_id).delete()
    db.query(Team).filter(Team.id == team_id).delete()


# ---------------------------------------------------------------------------
# User management (extended)
# ---------------------------------------------------------------------------


def list_users(
    db: Session,
    *,
    org_id: str | None = None,
    team_id: str | None = None,
    is_active: bool = True,
) -> list[User]:
    """List users, optionally filtered by org/team membership and active status."""
    query = db.query(User).filter(User.is_active == is_active)
    if org_id:
        query = query.join(OrgMembership).filter(OrgMembership.org_id == org_id)
    if team_id:
        query = query.join(TeamMembership).filter(TeamMembership.team_id == team_id)
    return query.all()


def update_user(db: Session, user_id: str, **kwargs) -> User:
    """Update mutable fields on a user."""
    user = db.query(User).filter(User.id == user_id).one()
    for key, value in kwargs.items():
        if hasattr(user, key) and key not in ("id", "created_at", "password_hash"):
            setattr(user, key, value)
    return user


def deactivate_user(db: Session, user_id: str) -> None:
    """Soft-delete a user by setting is_active=False."""
    user = db.query(User).filter(User.id == user_id).one()
    user.is_active = False


def set_user_role(
    db: Session,
    user_id: str,
    org_id: str | None = None,
    team_id: str | None = None,
    role: str = "member",
) -> None:
    """Set or update a user's role in an org and/or team."""
    if org_id:
        mem = db.query(OrgMembership).filter_by(user_id=user_id, org_id=org_id).first()
        if mem:
            mem.role = role
        else:
            db.add(OrgMembership(user_id=user_id, org_id=org_id, role=role))
    if team_id:
        mem = (
            db.query(TeamMembership).filter_by(user_id=user_id, team_id=team_id).first()
        )
        if mem:
            mem.role = role
        else:
            db.add(TeamMembership(user_id=user_id, team_id=team_id, role=role))


# ---------------------------------------------------------------------------
# Group mapping CRUD
# ---------------------------------------------------------------------------


def list_group_mappings(db: Session, org_id: str) -> list[EntraGroupMapping]:
    """List EntraID group mappings for an organization."""
    return db.query(EntraGroupMapping).filter(EntraGroupMapping.org_id == org_id).all()


def upsert_group_mapping(
    db: Session,
    entra_group_id: str,
    org_id: str,
    team_id: str | None = None,
    role: str = "member",
) -> EntraGroupMapping:
    """Create or update an EntraID group mapping."""
    mapping = (
        db.query(EntraGroupMapping)
        .filter(EntraGroupMapping.entra_group_id == entra_group_id)
        .first()
    )
    if mapping:
        mapping.org_id = org_id
        mapping.team_id = team_id
        mapping.role = role
    else:
        mapping = EntraGroupMapping(
            entra_group_id=entra_group_id,
            org_id=org_id,
            team_id=team_id,
            role=role,
        )
        db.add(mapping)
    return mapping


def delete_group_mapping(db: Session, entra_group_id: str) -> None:
    """Delete an EntraID group mapping."""
    db.query(EntraGroupMapping).filter(
        EntraGroupMapping.entra_group_id == entra_group_id
    ).delete()


# ---------------------------------------------------------------------------
# API Key Vault CRUD
# ---------------------------------------------------------------------------


def list_vault_keys(db: Session, owner_type: str, owner_id: str) -> list[dict]:
    """List vault key metadata (not decrypted values) for an owner."""
    keys = (
        db.query(ApiKeyVault)
        .filter(
            ApiKeyVault.owner_type == owner_type,
            ApiKeyVault.owner_id == owner_id,
        )
        .all()
    )
    return [
        {
            "id": k.id,
            "owner_type": k.owner_type,
            "owner_id": k.owner_id,
            "key_name": k.key_name,
            "created_at": k.created_at.isoformat() if k.created_at else None,
        }
        for k in keys
    ]


def store_vault_key(
    db: Session,
    owner_type: str,
    owner_id: str,
    key_name: str,
    plaintext_value: str,
) -> ApiKeyVault:
    """Encrypt and store an API key in the vault (upsert)."""
    encrypted = vault_crypto.encrypt(plaintext_value, purpose="api_key_vault")
    existing = (
        db.query(ApiKeyVault)
        .filter_by(owner_type=owner_type, owner_id=owner_id, key_name=key_name)
        .first()
    )
    if existing:
        existing.encrypted_value = encrypted
        return existing
    entry = ApiKeyVault(
        id=str(uuid.uuid4()),
        owner_type=owner_type,
        owner_id=owner_id,
        key_name=key_name,
        encrypted_value=encrypted,
    )
    db.add(entry)
    return entry


def get_vault_key_value(db: Session, vault_id: str) -> str:
    """Decrypt and return a vault key's plaintext value."""
    entry = db.query(ApiKeyVault).filter(ApiKeyVault.id == vault_id).one()
    return vault_crypto.decrypt(entry.encrypted_value, purpose="api_key_vault")


def delete_vault_key(db: Session, vault_id: str) -> None:
    """Delete a vault key entry."""
    db.query(ApiKeyVault).filter(ApiKeyVault.id == vault_id).delete()


def resolve_api_key(
    db: Session,
    key_name: str,
    user_id: str,
    team_id: str,
    org_id: str,
) -> str | None:
    """Resolve an API key by cascading: user → team → org → system."""
    for owner_type, owner_id in [
        ("user", user_id),
        ("team", team_id),
        ("org", org_id),
        ("system", "system"),
    ]:
        entry = (
            db.query(ApiKeyVault)
            .filter_by(owner_type=owner_type, owner_id=owner_id, key_name=key_name)
            .first()
        )
        if entry:
            return vault_crypto.decrypt(entry.encrypted_value, purpose="api_key_vault")
    return None


# ---------------------------------------------------------------------------
# MCP Service Registry CRUD
# ---------------------------------------------------------------------------


def list_services(db: Session, org_id: str | None = None) -> list[McpServiceRegistry]:
    """List MCP services, optionally scoped to an org (None = system-wide only)."""
    query = db.query(McpServiceRegistry).filter(McpServiceRegistry.is_enabled == True)  # noqa: E712
    if org_id:
        query = query.filter(
            (McpServiceRegistry.org_id == org_id) | (McpServiceRegistry.org_id == None)  # noqa: E711
        )
    else:
        query = query.filter(McpServiceRegistry.org_id == None)  # noqa: E711
    return query.all()


def get_service(db: Session, service_id: str) -> McpServiceRegistry | None:
    """Look up an MCP service by primary key."""
    return (
        db.query(McpServiceRegistry).filter(McpServiceRegistry.id == service_id).first()
    )


def create_service(db: Session, **kwargs) -> McpServiceRegistry:
    """Create an MCP service registry entry."""
    # Encrypt client_secret if provided
    if "client_secret" in kwargs:
        secret = kwargs.pop("client_secret")
        if secret:
            kwargs["client_secret_encrypted"] = vault_crypto.encrypt(
                secret, purpose="mcp_service_credentials"
            )
    service = McpServiceRegistry(id=str(uuid.uuid4()), **kwargs)
    db.add(service)
    return service


def update_service(db: Session, service_id: str, **kwargs) -> McpServiceRegistry:
    """Update an MCP service registry entry."""
    service = (
        db.query(McpServiceRegistry).filter(McpServiceRegistry.id == service_id).one()
    )
    # Handle client_secret encryption
    if "client_secret" in kwargs:
        secret = kwargs.pop("client_secret")
        if secret:
            kwargs["client_secret_encrypted"] = vault_crypto.encrypt(
                secret, purpose="mcp_service_credentials"
            )
    for key, value in kwargs.items():
        if hasattr(service, key) and key not in ("id", "created_at"):
            setattr(service, key, value)
    return service


def delete_service(db: Session, service_id: str) -> None:
    """Delete an MCP service and its connections."""
    db.query(McpConnection).filter(McpConnection.service_id == service_id).delete()
    db.query(McpServiceRegistry).filter(McpServiceRegistry.id == service_id).delete()


# ---------------------------------------------------------------------------
# MCP Connection CRUD
# ---------------------------------------------------------------------------


def get_connection(db: Session, user_id: str, service_id: str) -> McpConnection | None:
    """Look up a user's connection to an MCP service."""
    return (
        db.query(McpConnection)
        .filter_by(user_id=user_id, service_id=service_id)
        .first()
    )


def list_connections(db: Session, user_id: str) -> list[McpConnection]:
    """List all MCP connections for a user."""
    return db.query(McpConnection).filter(McpConnection.user_id == user_id).all()


def upsert_connection(
    db: Session, user_id: str, service_id: str, **kwargs
) -> McpConnection:
    """Create or update an MCP connection."""
    conn = get_connection(db, user_id, service_id)
    if conn:
        for key, value in kwargs.items():
            if hasattr(conn, key) and key not in ("id", "user_id", "service_id"):
                setattr(conn, key, value)
    else:
        conn = McpConnection(
            id=str(uuid.uuid4()),
            user_id=user_id,
            service_id=service_id,
            **kwargs,
        )
        db.add(conn)
    return conn


def delete_connection(db: Session, user_id: str, service_id: str) -> None:
    """Delete an MCP connection (also removes associated vault entries)."""
    conn = get_connection(db, user_id, service_id)
    if conn:
        # Clean up vault entries
        for vault_id in [
            conn.access_token_vault_id,
            conn.refresh_token_vault_id,
            conn.client_info_vault_id,
        ]:
            if vault_id:
                db.query(ApiKeyVault).filter(ApiKeyVault.id == vault_id).delete()
        db.query(McpConnection).filter(McpConnection.id == conn.id).delete()
