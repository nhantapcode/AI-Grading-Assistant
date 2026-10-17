from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from app.core.config import settings


class MemberChange(BaseModel):
    updated_at: datetime
    role: Literal['admin','trainer'] | None = None
    display_name_override: str | None = Field(default=None,max_length=120)

    @field_validator('display_name_override')
    @classmethod
    def name(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class CriterionInput(BaseModel):
    title: str = Field(min_length=1,max_length=200)
    description: str = Field(default='',max_length=5000)
    max_points: Decimal = Field(gt=0,le=99999999,decimal_places=2)


class ReferenceInput(BaseModel):
    title: str = Field(min_length=1,max_length=200)
    answer_text: str = Field(default='',max_length=200000)
    file_ids: list[UUID] = Field(default_factory=list,max_length=settings.max_upload_files)


class AssignmentInput(BaseModel):
    title: str = Field(min_length=1,max_length=200)
    description: str = Field(default='',max_length=10000)

    @field_validator('title')
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Title is required')
        return value.strip()


class VersionInput(AssignmentInput):
    updated_at: datetime
    instructions: str = Field(default='',max_length=200000)
    max_score: Decimal = Field(gt=0,le=99999999,decimal_places=2)
    exemplar_threshold_percent: Decimal = Field(default=80,ge=0,le=100,decimal_places=2)
    criteria: list[CriterionInput] = Field(default_factory=list,max_length=100)
    references: list[ReferenceInput] = Field(default_factory=list,max_length=20)
    file_ids: list[UUID] = Field(default_factory=list,max_length=settings.max_upload_files)


class StudentInput(BaseModel):
    external_student_id: str = Field(min_length=1,max_length=120)
    display_name: str = Field(min_length=1,max_length=120)
    email: str | None = Field(default=None,max_length=254)

    @field_validator('external_student_id','display_name')
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('This field is required')
        return value.strip()


class SubmissionInput(BaseModel):
    assignment_version_id: UUID
    student_id: UUID
    file_ids: list[UUID] = Field(min_length=1,max_length=settings.max_upload_files)
    idempotency_key: str = Field(min_length=16,max_length=128)
