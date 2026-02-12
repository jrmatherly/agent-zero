"""SQLAlchemy ORM models and CRUD operations for the multi-tenant auth database.

Defines eight models covering organizations, teams, users, memberships,
chat ownership, API key vaulting, and EntraID group mappings.  All models
inherit from the shared ``Base`` declared in :mod:`python.helpers.auth_db`.
"""

import uuid
from datetime import datetime, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Session, relationship

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

    # Track which (org, team) combos the user should belong to
    desired_memberships: set[tuple[str, str]] = set()

    for mapping in current_mappings:
        if mapping.org_id:
            # Ensure org membership exists
            org_mem = (
                db.query(OrgMembership)
                .filter_by(user_id=user.id, org_id=mapping.org_id)
                .first()
            )
            if not org_mem:
                org_mem = OrgMembership(
                    user_id=user.id,
                    org_id=mapping.org_id,
                    role=mapping.role,
                )
                db.add(org_mem)
            else:
                org_mem.role = mapping.role

        if mapping.team_id:
            desired_memberships.add((mapping.org_id, mapping.team_id))
            team_mem = (
                db.query(TeamMembership)
                .filter_by(user_id=user.id, team_id=mapping.team_id)
                .first()
            )
            if not team_mem:
                team_mem = TeamMembership(
                    user_id=user.id,
                    team_id=mapping.team_id,
                    role=mapping.role,
                )
                db.add(team_mem)
            else:
                team_mem.role = mapping.role

    # Remove team memberships for groups user is no longer in
    # (only remove those that were originally created via group sync)
    all_mapped_team_ids = {
        m.team_id for m in db.query(EntraGroupMapping).all() if m.team_id
    }
    current_team_mems = (
        db.query(TeamMembership)
        .filter(
            TeamMembership.user_id == user.id,
            TeamMembership.team_id.in_(all_mapped_team_ids),
        )
        .all()
    )
    for mem in current_team_mems:
        if mem.team_id not in {t for _, t in desired_memberships}:
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
