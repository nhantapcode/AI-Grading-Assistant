"""Public request/response schemas exclude stored credentials."""
from pydantic import BaseModel, Field

from app.models.user import User


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str

    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        return cls(id=str(user.id), email=user.email, display_name=user.display_name)
