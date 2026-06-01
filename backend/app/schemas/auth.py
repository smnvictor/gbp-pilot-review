from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    business_name: str = Field(min_length=2, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


class EmailVerify(BaseModel):
    token: str


class UserPublic(BaseModel):
    id: UUID
    email: EmailStr
    role: str
    email_verified_at: datetime | None = None
    client_id: UUID | None = None

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    business_name: str | None = Field(default=None, max_length=200)
