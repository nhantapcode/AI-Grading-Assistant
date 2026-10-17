from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID


@dataclass(frozen=True)
class Invitation:
    id: UUID
    organization_id: UUID
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    invited_by: UUID | None = None
    invited_by_name: str | None = None

    @property
    def status(self) -> str:
        if self.accepted_at:
            return "accepted"
        if self.revoked_at:
            return "revoked"
        return "expired" if self.expires_at <= datetime.now(timezone.utc) else "pending"
