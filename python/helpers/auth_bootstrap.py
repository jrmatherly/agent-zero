"""Bootstrap the auth database on first launch.

Ensures the database exists, runs Alembic migrations to head, and seeds
the default organization, team, and admin user when environment variables
are configured.

Call :func:`bootstrap` once at application startup (from ``run_ui.py``).
"""

import os

from alembic import command
from alembic.config import Config

from python.helpers import auth_db, user_store
from python.helpers.print_style import PrintStyle


def _run_migrations() -> None:
    """Run Alembic migrations to head."""
    alembic_cfg = Config("alembic.ini")
    db_url = os.environ.get("AUTH_DATABASE_URL", "sqlite:///usr/auth.db")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")


def _seed_defaults() -> None:
    """Create the default org, team, and admin user if they don't exist."""
    with auth_db.get_session() as db:
        # Check if any organization exists (idempotent)
        existing_org = db.query(user_store.Organization).first()
        if existing_org:
            PrintStyle.info(
                "Auth bootstrap: default org already exists, skipping seed."
            )
            return

        # Create default org and team
        org = user_store.create_organization(db, name="Default Org", slug="default")
        team = user_store.create_team(
            db, org_id=org.id, name="Default Team", slug="default"
        )
        PrintStyle.info(
            f"Auth bootstrap: created org '{org.name}' and team '{team.name}'"
        )

        # Create admin user if ADMIN_EMAIL is set
        admin_email = os.environ.get("ADMIN_EMAIL")
        admin_password = os.environ.get("ADMIN_PASSWORD")
        if admin_email and admin_password:
            admin = user_store.create_local_user(
                db,
                email=admin_email,
                password=admin_password,
                is_system_admin=True,
            )
            # Add admin to default org as owner
            membership = user_store.OrgMembership(
                user_id=admin.id,
                org_id=org.id,
                role="owner",
            )
            db.add(membership)
            # Add admin to default team as lead
            team_membership = user_store.TeamMembership(
                user_id=admin.id,
                team_id=team.id,
                role="lead",
            )
            db.add(team_membership)
            PrintStyle.info(f"Auth bootstrap: created admin user '{admin_email}'")
        elif admin_email:
            PrintStyle.warning(
                "Auth bootstrap: ADMIN_EMAIL is set but ADMIN_PASSWORD is missing. "
                "Skipping admin account creation."
            )


def _seed_group_mappings() -> None:
    """Seed Entra ID group-to-org/team mappings from environment variable.

    Reads ``A0_SET_SSO_GROUP_MAPPINGS`` which contains semicolon-delimited
    entries of the form ``entra_group_id:org_slug:team_slug:role``.
    ``team_slug`` and ``role`` are optional (defaults: no team, role="member").
    """
    raw = os.environ.get("A0_SET_SSO_GROUP_MAPPINGS", "")
    if not raw.strip():
        return

    entries = raw.split(";")
    count = 0

    with auth_db.get_session() as db:
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue

            fields = [f.strip() for f in entry.split(":")]
            if len(fields) < 2:
                PrintStyle.warning(
                    f"Auth bootstrap: skipping malformed group mapping "
                    f"(need at least 2 fields): '{entry}'"
                )
                continue

            entra_group_id = fields[0]
            org_slug = fields[1]
            team_slug = fields[2] if len(fields) > 2 else ""
            role = fields[3] if len(fields) > 3 else "member"

            if not entra_group_id or not org_slug:
                PrintStyle.warning(
                    f"Auth bootstrap: skipping group mapping with empty "
                    f"required fields: '{entry}'"
                )
                continue

            # Resolve org by slug
            org = db.query(user_store.Organization).filter_by(slug=org_slug).first()
            if not org:
                PrintStyle.warning(
                    f"Auth bootstrap: org '{org_slug}' not found, "
                    f"skipping group mapping for '{entra_group_id}'"
                )
                continue

            # Resolve team by (org_id, slug) if provided
            team_id = None
            if team_slug:
                team = (
                    db.query(user_store.Team)
                    .filter_by(org_id=org.id, slug=team_slug)
                    .first()
                )
                if not team:
                    PrintStyle.warning(
                        f"Auth bootstrap: team '{team_slug}' not found in "
                        f"org '{org_slug}', skipping group mapping for "
                        f"'{entra_group_id}'"
                    )
                    continue
                team_id = team.id

            user_store.upsert_group_mapping(
                db,
                entra_group_id=entra_group_id,
                org_id=org.id,
                team_id=team_id,
                role=role,
            )
            count += 1

    if count:
        PrintStyle.info(
            f"Auth bootstrap: seeded {count} group mapping(s) from environment."
        )


def bootstrap() -> None:
    """Initialize auth database and seed defaults.

    Safe to call multiple times -- idempotent.  Skips seeding if the
    default organization already exists.
    """
    # Initialize the database engine
    auth_db.init_db()

    # Run migrations
    PrintStyle.info("Auth bootstrap: running database migrations...")
    _run_migrations()

    # Seed defaults
    _seed_defaults()

    # Seed SSO group mappings from environment
    _seed_group_mappings()

    # Initialize RBAC enforcer and seed default policies
    try:
        from python.helpers import rbac

        rbac.init_enforcer()
        rbac.seed_default_policies()

        # Sync admin user roles if admin exists
        admin_email = os.environ.get("ADMIN_EMAIL")
        if admin_email:
            with auth_db.get_session() as db:
                admin = user_store.get_user_by_email(db, admin_email)
                if admin:
                    rbac.sync_user_roles(admin.id)
    except Exception as e:
        PrintStyle.warning(f"RBAC initialization skipped: {e}")

    PrintStyle.info("Auth bootstrap: complete.")
