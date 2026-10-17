"""Record mapped from the existing users table."""
from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class User:
    id: UUID
    email: str
    display_name: str
    password_hash: str | None = field(default=None, repr=False)
    status: str = "active"
