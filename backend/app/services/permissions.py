from app.models.workspace import OrganizationAccess
from app.services.errors import WorkspaceError


def ensure_role(role: str | None, allowed: tuple[str, ...]) -> None:
    if role not in allowed:
        raise WorkspaceError(403, 'You do not have permission to perform this action')


def ensure_access_role(access: OrganizationAccess, *roles: str) -> OrganizationAccess:
    ensure_role(access.role,roles)
    return access
