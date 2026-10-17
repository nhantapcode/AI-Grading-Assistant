"""Authentication rules independent of HTTP requests and cookies."""
import secrets
from datetime import datetime, timedelta, timezone

from app.core.security import password_hash, token_hash, verify_password
from app.models.auth_session import AuthSession
from app.models.user import User
from app.repositories.sessions import SessionRepository
from app.repositories.users import UserRepository


class AuthenticationError(Exception):
    """Credentials or session cannot authenticate a user."""


class UserNotFoundError(Exception):
    """Password management requires an existing local user."""


class AuthService:
    def __init__(self, users: UserRepository, sessions: SessionRepository, session_seconds: int) -> None:
        self.users = users
        self.sessions = sessions
        self.session_seconds = session_seconds

    def login(self, email: str, password: str, previous_token: str | None = None) -> tuple[User, str]:
        user = self.users.find_local_by_email(email.strip().lower())
        valid = verify_password(password, user.password_hash if user else None)
        if not user or not valid or user.status != "active":
            raise AuthenticationError("Email or password is incorrect")
        self.logout(previous_token)
        token = secrets.token_urlsafe(32)
        self.sessions.create(AuthSession(
            user_id=user.id,
            refresh_token_hash=token_hash(token),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.session_seconds),
        ))
        return user, token

    def current_user(self, token: str | None) -> User:
        if not token:
            raise AuthenticationError("Please sign in")
        user = self.sessions.find_active_user(token_hash(token))
        if not user:
            raise AuthenticationError("Your session has expired. Please sign in again")
        return user

    def logout(self, token: str | None) -> None:
        if token:
            self.sessions.revoke(token_hash(token))

    def set_password(self, email: str, password: str) -> None:
        if len(password) < 12:
            raise ValueError("Password must contain at least 12 characters")
        user_id = self.users.update_password(email.strip().lower(), password_hash.hash(password))
        if user_id is None:
            raise UserNotFoundError("Local user not found; import sample data first")
        self.sessions.revoke_for_user(user_id)
