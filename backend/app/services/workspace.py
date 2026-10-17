from uuid import UUID

from app.models.workspace import OrganizationAccess
from app.repositories.workspace import WorkspaceRepository
from app.services.errors import WorkspaceError
from app.schemas.workspace import MemberChange
from app.services.permissions import ensure_access_role


def require_access(repository: WorkspaceRepository, org: UUID, user: UUID) -> OrganizationAccess:
    access = repository.access(org,user)
    if not access:
        raise WorkspaceError(403, 'You no longer have access to this organization')
    return access


class AccountService:
    def __init__(self, repository: WorkspaceRepository, access: OrganizationAccess) -> None:
        self.repository = repository
        self.access = access

    def change(self, user: UUID, body: MemberChange, operation: str) -> dict:
        ensure_access_role(self.access,'owner')
        member = self.repository.member(self.access.organization_id,user)
        if not member:
            raise WorkspaceError(404, 'Member not found')
        if member['role'] == 'owner' or user == self.access.user_id:
            raise WorkspaceError(403, 'Owner access cannot be changed here')
        if member['updated_at'] != body.updated_at:
            raise WorkspaceError(409, 'This account changed. Refresh and try again')
        if operation == 'restore' and not body.role:
            raise WorkspaceError(422,'Choose a role when restoring access')
        status = {'edit':member['status'],'revoke':'revoked','restore':'active'}[operation]
        role = member['role'] if operation == 'revoke' else body.role or member['role']
        name = body.display_name_override if operation == 'edit' else member['display_name_override']
        result = self.repository.change_member(self.access.organization_id,user,role,name,status)
        if status == 'revoked':
            self.repository.revoke_invitations(self.access.organization_id,user)
        self.repository.audit(self.access,f'membership.{operation}','membership',user)
        return result
