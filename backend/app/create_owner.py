"""Bootstrap a new organization and its first owner in one transaction."""
import argparse
import getpass

import psycopg
from psycopg.rows import dict_row

from app.core.config import settings
from app.core.security import password_hash
from app.schemas.invitations import InvitationRequest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    if not args.organization.strip() or not args.name.strip():
        parser.error("Organization and name must not be empty")
    try:
        email = InvitationRequest(email=args.email, role="admin").email
    except ValueError:
        parser.error("Invalid email")
    password = getpass.getpass("Password (at least 12 characters): ")
    if len(password) < 12 or len(password) > 1024:
        parser.error("Password must contain 12–1024 characters")
    if password != getpass.getpass("Confirm password: "):
        parser.error("Passwords do not match")
    try:
        with psycopg.connect(settings.database_url, row_factory=dict_row) as db:
            user = db.execute("INSERT INTO users(email,display_name,password_hash) VALUES (%s,%s,%s) RETURNING id",
                              (email,args.name.strip(),password_hash.hash(password))).fetchone()
            org = db.execute("INSERT INTO organizations(name) VALUES (%s) RETURNING id", (args.organization.strip(),)).fetchone()
            db.execute("INSERT INTO memberships(organization_id,user_id,role) VALUES (%s,%s,'owner')", (org["id"],user["id"]))
    except psycopg.errors.UniqueViolation:
        parser.error("Email already exists. Use a new email for bootstrap; no records were created.")
    print(f"Owner created. Organization ID: {org['id']}")


if __name__ == "__main__":
    main()
