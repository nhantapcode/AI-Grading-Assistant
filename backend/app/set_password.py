"""Set a local user's password without placing the password in shell history."""
import argparse
import getpass

import psycopg
from psycopg.rows import dict_row

from app.core.config import settings
from app.repositories.sessions import SessionRepository
from app.repositories.users import UserRepository
from app.services.auth import AuthService, UserNotFoundError


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    args = parser.parse_args()
    password = getpass.getpass("New password (at least 12 characters): ")
    if len(password) < 12:
        parser.error("Password must contain at least 12 characters")
    if password != getpass.getpass("Confirm password: "):
        parser.error("Passwords do not match")
    try:
        with psycopg.connect(settings.database_url, row_factory=dict_row) as db:
            service = AuthService(UserRepository(db), SessionRepository(db), settings.session_seconds)
            service.set_password(args.email, password)
    except (UserNotFoundError, ValueError) as error:
        parser.error(str(error))
    print("Password updated and existing sessions revoked.")


if __name__ == "__main__":
    main()
