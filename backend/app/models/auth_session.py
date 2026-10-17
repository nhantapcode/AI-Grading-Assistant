from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class AuthSession:
    user_id: UUID
    refresh_token_hash: str = field(repr=False)
    expires_at: datetime
