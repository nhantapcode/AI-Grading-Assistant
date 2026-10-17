from uuid import UUID

from psycopg import Connection

from app.models.auth_session import AuthSession
from app.models.user import User


class SessionRepository:
    def __init__(self, db: Connection) -> None:
        self.db = db

    def create(self, session: AuthSession) -> None:
        self.db.execute(
            "INSERT INTO auth_sessions(user_id, refresh_token_hash, expires_at) VALUES (%s,%s,%s)",
            (session.user_id, session.refresh_token_hash, session.expires_at),
        )

    def find_active_user(self, digest: str) -> User | None:
        row = self.db.execute(
            """SELECT u.id, u.email, u.display_name FROM auth_sessions s JOIN users u ON u.id=s.user_id
            WHERE s.refresh_token_hash=%s AND s.revoked_at IS NULL AND s.expires_at>now() AND u.status='active'""",
            (digest,),
        ).fetchone()
        return User(**row) if row else None

    def revoke(self, digest: str) -> None:
        self.db.execute(
            "UPDATE auth_sessions SET revoked_at=now() WHERE refresh_token_hash=%s AND revoked_at IS NULL",
            (digest,),
        )

    def revoke_for_user(self, user_id: UUID) -> None:
        self.db.execute(
            "UPDATE auth_sessions SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL", (user_id,)
        )
