import secrets
from dataclasses import asdict
from uuid import UUID

from app.core.security import password_hash, token_hash
from app.models.user import User
from app.models.invitation import Invitation
from app.repositories.invitations import InvitationRepository
from app.repositories.memberships import MembershipRepository
from app.services.permissions import ensure_role


class InvitationError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class InvitationService:
    def __init__(self, invitations: InvitationRepository, memberships: MembershipRepository) -> None:
        self.invitations = invitations
        self.memberships = memberships

    def require_manager(self, organization_id: UUID, user_id: UUID, invited_role: str | None = None) -> str:
        role = self.memberships.manager_role(organization_id, user_id)
        ensure_role(role,('owner',) if invited_role == 'admin' else ('owner','admin'))
        return role

    def create(self, organization_id: UUID, user: User, email: str, role: str) -> dict:
        self.require_manager(organization_id, user.id, role)
        token = secrets.token_urlsafe(32)
        invitation = self.invitations.create(organization_id, email, role, token_hash(token), user.id)
        return {**asdict(invitation), "status": invitation.status, "token": token}

    def list(self, organization_id: UUID, user: User) -> list[dict]:
        self.require_manager(organization_id, user.id)
        return [{**asdict(item), "status": item.status} for item in self.invitations.list(organization_id)]

    def revoke(self, organization_id: UUID, invitation_id: UUID, user: User) -> None:
        self.require_manager(organization_id, user.id)
        if not self.invitations.revoke(organization_id, invitation_id):
            raise InvitationError(409, "Invitation not found or already processed")

    def valid_invitation(self, token: str) -> tuple[Invitation, str]:
        result = self.invitations.lock_token(token_hash(token))
        if not result:
            raise InvitationError(404, "Invalid invitation link")
        invitation, invited_by, organization_name = result
        if invitation.status != "pending":
            messages = {"expired": "This invitation has expired", "accepted": "This invitation has already been used", "revoked": "This invitation has been revoked"}
            raise InvitationError(410, messages[invitation.status])
        self.require_manager(invitation.organization_id, invited_by, invitation.role)
        return invitation, organization_name

    def resolve(self, token: str) -> dict:
        invitation, name = self.valid_invitation(token)
        return {"email": invitation.email, "role": invitation.role, "organization_name": name,
                "expires_at": invitation.expires_at, "account_exists": self.invitations.find_user(invitation.email) is not None}

    def accept(self, token: str, current_user: User | None, name: str | None, password: str | None) -> dict:
        invitation, _ = self.valid_invitation(token)
        existing = self.invitations.find_user(invitation.email)
        if current_user and current_user.email != invitation.email:
            raise InvitationError(403, "Please sign in with the invited email")
        if existing:
            if not current_user or current_user.id != existing["id"] or existing["status"] != "active":
                raise InvitationError(401, "Please sign in with the invited email to accept")
            user_id = current_user.id
        else:
            if not name or not name.strip() or not password or len(password) < 12:
                raise InvitationError(422, "Enter your name and a password with at least 12 characters")
            user_id = self.invitations.create_user(invitation.email, name.strip(), password_hash.hash(password))
            if user_id is None:
                raise InvitationError(409, "The account was just created. Please sign in to accept the invitation")
        if not self.memberships.add(invitation.organization_id, user_id, invitation.role):
            raise InvitationError(409, "This account already has a membership in the organization. Contact your administrator")
        self.invitations.accept(invitation.id)
        return {"message": "You have joined the organization", "email": invitation.email}
