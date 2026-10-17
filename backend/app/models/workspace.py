from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class OrganizationAccess:
    organization_id: UUID
    user_id: UUID
    role: str

    @property
    def is_manager(self) -> bool:
        return self.role in ('owner', 'admin')
