"""User SQL operations. The caller owns the transaction."""
from uuid import UUID

from psycopg import Connection

from app.models.user import User


class UserRepository:
    def __init__(self, db: Connection) -> None:
        self.db = db

    def find_local_by_email(self, email: str) -> User | None:
        row = self.db.execute(
            "SELECT id, email, display_name, password_hash, status FROM users WHERE email=%s AND identity_provider='local'",
            (email,),
        ).fetchone()
        return User(**row) if row else None

    def update_password(self, email: str, encoded_password: str) -> UUID | None:
        row = self.db.execute(
            "UPDATE users SET password_hash=%s WHERE email=%s AND identity_provider='local' RETURNING id",
            (encoded_password, email),
        ).fetchone()
        return row["id"] if row else None
