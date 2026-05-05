"""
Seed script.

Creates the three roles (writer/editor/admin) and a bootstrap admin user.

Real content is scraped from awgp.org on demand — pass `--awgp` (or set
`SEED_FROM_AWGP=true`) to pull the latest ~50 articles + images into the
DB right after the admin is created.

Usage:
    python scripts/seed.py                       # roles + admin only
    python scripts/seed.py --awgp                # + scrape awgp.org (wipes existing posts)
    python scripts/seed.py --awgp --limit 20     # scrape fewer
    python scripts/seed.py --awgp --no-wipe      # scrape without wiping

Env:
    ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_NAME   (optional admin overrides)
    SEED_FROM_AWGP=true                       (equivalent to passing --awgp)
"""
import argparse
import os
import sys
from pathlib import Path

# Make the app package importable when running as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.models.role import Role
from app.models.user import User
from app.utils.enums import RoleName


def _seed_roles():
    for role_name in RoleName.values():
        if not Role.objects(name=role_name).first():
            Role(name=role_name, description=f"{role_name.title()} role").save()
    print("[seed] Roles ready:", RoleName.values())


def _seed_admin() -> User:
    email = os.getenv("ADMIN_EMAIL", "admin@dsvv.ac.in")
    password = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")
    name = os.getenv("ADMIN_NAME", "DSVV Admin")

    admin = User.objects(email=email).first()
    if admin:
        print(f"[seed] Admin already exists: {email}")
        return admin

    admin = User(name=name, email=email)
    admin.set_password(password)
    admin_role = Role.objects(name=RoleName.ADMIN.value).first()
    if admin_role:
        admin.roles.append(admin_role)
    admin.save()
    print(f"[seed] Admin created: {email} / {password}")
    return admin


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Seed roles + admin (optionally scrape awgp.org).")
    parser.add_argument("--awgp", action="store_true",
                        help="After seeding, scrape awgp.org/en/news and import articles.")
    parser.add_argument("--limit", type=int, default=50,
                        help="Max articles to import when --awgp is set (default 50).")
    parser.add_argument("--no-wipe", dest="wipe", action="store_false",
                        help="Do NOT delete existing posts/media before the awgp import.")
    parser.set_defaults(wipe=True)
    return parser.parse_args(argv)


def seed(argv=None):
    args = _parse_args(argv)
    scrape_flag = args.awgp or os.getenv("SEED_FROM_AWGP", "").lower() == "true"

    app = create_app()
    with app.app_context():
        _seed_roles()
        _seed_admin()

        if scrape_flag:
            # Import lazily so a missing bs4/requests install doesn't break
            # the default (roles+admin only) seed path.
            from scripts.scrape_awgp import run_scrape
            run_scrape(limit=args.limit, wipe=args.wipe, verbose=True)


if __name__ == "__main__":
    seed()
