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

    PrintStyle.info("Auth bootstrap: complete.")
