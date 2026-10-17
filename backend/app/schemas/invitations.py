import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class InvitationRequest(BaseModel):
    email: str = Field(max_length=254)
    role: Literal["admin", "trainer"]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Invalid email address")
        return value


class TokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=128)


class AcceptRequest(TokenRequest):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=12, max_length=1024)
