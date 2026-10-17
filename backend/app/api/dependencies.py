from fastapi import Depends, HTTPException, Request
from collections.abc import Callable
from uuid import UUID
from psycopg import Connection

from app.core.config import settings
from app.db.connection import get_db
from app.repositories.sessions import SessionRepository
from app.repositories.users import UserRepository
from app.services.auth import AuthService
from app.models.user import User
from app.models.workspace import OrganizationAccess
from app.repositories.workspace import WorkspaceRepository
from app.services.workspace import require_access
from app.services.permissions import ensure_access_role
from app.repositories.rate_limits import RateLimitRepository
from app.schemas.auth import LoginRequest
from app.services.rate_limits import LoginRateLimiter
from psycopg import OperationalError


def get_auth_service(db: Connection = Depends(get_db)) -> AuthService:
    return AuthService(UserRepository(db), SessionRepository(db), settings.session_seconds)


def get_login_limiter() -> LoginRateLimiter:
    return LoginRateLimiter(RateLimitRepository(settings.database_url),settings.login_ip_limit,settings.login_account_limit,settings.login_window_seconds)


def limit_login(request: Request, body: LoginRequest, limiter: LoginRateLimiter = Depends(get_login_limiter)) -> None:
    address = request.client.host if request.client else 'unknown'
    try:
        retry_after = limiter.check(address,body.email)
    except OperationalError as error:
        raise HTTPException(503,'Login protection is temporarily unavailable',headers={'Retry-After':'5'}) from error
    if retry_after:
        raise HTTPException(429,'Too many sign-in attempts. Please try again later.',headers={'Retry-After':str(retry_after)})


def current_user(request: Request, auth: AuthService = Depends(get_auth_service)) -> User:
    return auth.current_user(request.cookies.get(settings.cookie_name))


def get_organization_access(organization_id: UUID, user: User = Depends(current_user), db: Connection = Depends(get_db)) -> OrganizationAccess:
    return require_access(WorkspaceRepository(db),organization_id,user.id)


def require_role(*roles: str) -> Callable[..., OrganizationAccess]:
    if not roles or any(role not in ('owner','admin','trainer') for role in roles):
        raise ValueError('Specify at least one supported organization role')

    def authorize(access: OrganizationAccess = Depends(get_organization_access)) -> OrganizationAccess:
        return ensure_access_role(access,*roles)

    return authorize


def protect_mutation(request: Request) -> None:
    # Custom headers force browsers to preflight cross-origin requests.
    if request.headers.get("x-requested-with") != "grading-web":
        raise HTTPException(403, "Missing request protection header")
    origin = request.headers.get("origin")
    if origin and origin != settings.frontend_origin:
        raise HTTPException(403, "Origin is not allowed")
