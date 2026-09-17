"""Pydantic schemas for recruiter authentication. Passwords are write-only."""
from __future__ import annotations

import re

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import normalize_email

_PASSWORD_HAS_LETTER = re.compile(r"[A-Za-z]")
_PASSWORD_HAS_DIGIT = re.compile(r"\d")


def _validate_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if _PASSWORD_HAS_LETTER.search(value) is None or _PASSWORD_HAS_DIGIT.search(value) is None:
        raise ValueError("Password must include at least one letter and one number.")
    return value


class RecruiterSignupRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("Full name is required.")
        return stripped

    @field_validator("email")
    @classmethod
    def normalize_signup_email(cls, value: EmailStr) -> str:
        return normalize_email(str(value))

    @field_validator("password")
    @classmethod
    def validate_signup_password(cls, value: str) -> str:
        return _validate_password(value)


class RecruiterLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_login_email(cls, value: EmailStr) -> str:
        return normalize_email(str(value))


class RecruiterPublic(BaseModel):
    id: int
    full_name: str
    email: str
    role: str


class RecruiterAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    recruiter: RecruiterPublic


class RecruiterForgotPasswordRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_forgot_password_email(cls, value: EmailStr) -> str:
        return normalize_email(str(value))


class RecruiterResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=512)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("token")
    @classmethod
    def strip_reset_token(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Reset token is required.")
        return stripped

    @field_validator("new_password")
    @classmethod
    def validate_reset_password(cls, value: str) -> str:
        return _validate_password(value)


class RecruiterPasswordResetResponse(BaseModel):
    message: str
