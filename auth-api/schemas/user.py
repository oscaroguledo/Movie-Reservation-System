import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class UserCreate(BaseModel):
    email: EmailStr
    type: str | None = Field(default="client", pattern="^(admin|client)$")
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "type": "client",
                "password": "StrongPassword123!",
            }
        }
    )

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, value: str) -> str:
        """Validates that password meets security complexity requirements."""
        if not re.search(r"[A-Z]", value):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", value):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", value):
            raise ValueError("Password must contain at least one digit.")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]", value):
            raise ValueError("Password must contain at least one special character.")
        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "password": "StrongPassword123!",
            }
        }
    )

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, value: str) -> str:
        """Validates that password meets security complexity requirements."""
        if not re.search(r"[A-Z]", value):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", value):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", value):
            raise ValueError("Password must contain at least one digit.")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]", value):
            raise ValueError("Password must contain at least one special character.")
        return value


class UserGet(BaseModel):
    id: UUID | None = None
    email: EmailStr | None = None
    type: str | None = Field(default=None, pattern="^(admin|client)$")
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "user@example.com",
                "type": "client",
            }
        }
    )

    @model_validator(mode="after")
    def validate_at_least_one_field_provided(self) -> "UserGet":
        """At least one filter field must be provided for a valid UserGet request."""
        if not any((self.id, self.email, self.type)):
            raise ValueError("At least one of id, email, type must be provided.")
        return self


class UserList(BaseModel):
    type: str | None = Field(default=None, pattern="^(admin|client)$")
    first_name: str | None = Field(default=None, min_length=1, max_length=50)
    last_name: str | None = Field(default=None, min_length=1, max_length=50)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "client",
                "first_name": "Jane",
                "last_name": "Doe",
            }
        }
    )

    @model_validator(mode="after")
    def validate_at_least_one_field_provided(self) -> "UserList":
        """At least one filter field must be provided for a valid UserList request."""
        if not any((self.type, self.first_name, self.last_name)):
            raise ValueError("At least one of type, first_name, last_name must be provided.")
        return self


class UserUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=50)
    last_name: str | None = Field(default=None, min_length=1, max_length=50)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    type: str | None = Field(default=None, pattern="^(admin|client)$")
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "first_name": "Jane",
                "last_name": "Doe",
                "password": "NewStrongPassword123!",
                "type": "client",
            }
        }
    )

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, value: str | None) -> str | None:
        """Validates that password meets security complexity requirements.

        password is optional here (unlike UserCreate/UserLogin), so an
        omitted or explicitly null value must pass through untouched
        rather than being run through checks that assume a string.
        """
        if value is None:
            return value
        if not re.search(r"[A-Z]", value):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", value):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", value):
            raise ValueError("Password must contain at least one digit.")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]", value):
            raise ValueError("Password must contain at least one special character.")
        return value
