from uuid import UUID

from fastapi import APIRouter, Depends, Request, Query
from typing import Literal
from psycopg import Connection

from app.api.dependencies import current_user, get_auth_service, protect_mutation, require_role
from app.core.config import settings
from app.db.connection import get_db
from app.models.user import User
from app.repositories.invitations import InvitationRepository
from app.repositories.memberships import MembershipRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.invitations import AcceptRequest, InvitationRequest, TokenRequest
from app.services.auth import AuthService
from app.services.invitations import InvitationService

router = APIRouter(tags=["Members and invitations"])


def invitation_service(db: Connection = Depends(get_db)) -> InvitationService:
    return InvitationService(InvitationRepository(db), MembershipRepository(db))


@router.get("/organizations")
def organizations(user: User = Depends(current_user), service: InvitationService = Depends(invitation_service)) -> list[dict]:
    return service.memberships.organizations(user.id)


@router.get("/organizations/{organization_id}/members", dependencies=[Depends(require_role('owner','admin'))])
def members(organization_id: UUID, user: User = Depends(current_user), service: InvitationService = Depends(invitation_service),
            page: int | None = Query(None,ge=1), limit: int = Query(20,ge=1,le=100), search: str = Query('',max_length=200),
            role: Literal['','owner','admin','trainer'] = '', status: Literal['','active','revoked'] = '', db: Connection = Depends(get_db)) -> list[dict] | dict:
    if page is not None:
        return WorkspaceRepository(db).members(organization_id,search,role,status,page,limit)
    return service.memberships.members(organization_id)


@router.post("/organizations/{organization_id}/invitations", status_code=201, dependencies=[Depends(protect_mutation),Depends(require_role('owner','admin'))])
def create(organization_id: UUID, body: InvitationRequest, user: User = Depends(current_user),
           service: InvitationService = Depends(invitation_service)) -> dict:
    result = service.create(organization_id, user, body.email, body.role)
    token = result.pop("token")
    result["link"] = f"{settings.frontend_origin}/#invite={token}"
    return result


@router.get("/organizations/{organization_id}/invitations", dependencies=[Depends(require_role('owner','admin'))])
def list_invitations(organization_id: UUID, user: User = Depends(current_user), service: InvitationService = Depends(invitation_service)) -> list[dict]:
    return service.list(organization_id, user)


@router.post("/organizations/{organization_id}/invitations/{invitation_id}/revoke", status_code=204, dependencies=[Depends(protect_mutation),Depends(require_role('owner','admin'))])
def revoke(organization_id: UUID, invitation_id: UUID, user: User = Depends(current_user), service: InvitationService = Depends(invitation_service)) -> None:
    service.revoke(organization_id, invitation_id, user)


@router.post("/invitations/resolve", dependencies=[Depends(protect_mutation)])
def resolve(body: TokenRequest, service: InvitationService = Depends(invitation_service)) -> dict:
    return service.resolve(body.token)


@router.post("/invitations/accept", dependencies=[Depends(protect_mutation)])
def accept(body: AcceptRequest, request: Request, auth: AuthService = Depends(get_auth_service),
           service: InvitationService = Depends(invitation_service)) -> dict:
    token = request.cookies.get(settings.cookie_name)
    user = auth.current_user(token) if token else None
    return service.accept(body.token, user, body.display_name, body.password)
