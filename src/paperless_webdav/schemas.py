# src/paperless_webdav/schemas.py
"""Pydantic schemas for API request/response validation."""

import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# Share name validation: alphanumeric with dashes, 1-63 chars, must start with alphanumeric
SHARE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,62}$")


class ShareCreate(BaseModel):
    """Schema for creating a new share."""

    name: Annotated[str, Field(min_length=1, max_length=63)]
    include_tags: list[str] = Field(default_factory=list, min_length=1)
    exclude_tags: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    read_only: bool = True
    done_folder_enabled: bool = False
    done_folder_name: str = "done"
    done_tag: str | None = None
    allowed_users: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate share name is alphanumeric with dashes only."""
        if not SHARE_NAME_PATTERN.match(v):
            raise ValueError(
                "Share name must start with alphanumeric and contain only "
                "alphanumeric characters and dashes (1-63 chars)"
            )
        return v

    @model_validator(mode="after")
    def validate_done_folder(self) -> "ShareCreate":
        """Validate done_tag is provided when done_folder_enabled is True."""
        if self.done_folder_enabled and not self.done_tag:
            raise ValueError("done_tag is required when done_folder_enabled is True")
        return self


class ShareUpdate(BaseModel):
    """Schema for updating an existing share."""

    include_tags: list[str] | None = None
    exclude_tags: list[str] | None = None
    expires_at: datetime | None = None
    read_only: bool | None = None
    done_folder_enabled: bool | None = None
    done_folder_name: str | None = None
    done_tag: str | None = None
    allowed_users: list[str] | None = None


class ShareResponse(BaseModel):
    """Schema for share response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    include_tags: list[str]
    exclude_tags: list[str]
    expires_at: datetime | None
    read_only: bool
    done_folder_enabled: bool
    done_folder_name: str
    done_tag: str | None
    allowed_users: list[str]
    created_at: datetime
    updated_at: datetime


class TagResponse(BaseModel):
    """Schema for tag response from Paperless-ngx."""

    id: int
    name: str
    slug: str
    color: str | None = None
    match: str | None = None
    matching_algorithm: int | None = None
    is_insensitive: bool = True
