from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from pydantic import field_validator
from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint, func
from sqlmodel import JSON, Field, SQLModel

from langflow.schema.serialize import UUIDstr
from langflow.services.database.models.custom_provider.schemas import ValidationStatus
from langflow.services.database.utils import validate_non_empty_string


class CustomProvider(SQLModel, table=True):  # type: ignore[call-arg]
    """A user-defined OpenAI-compatible model supplier.

    One row is one supplier. Credentials live here (encrypted), not as global
    Variables keyed by derived names -- the row owns identity, validation
    status, discovered and manual models, and deletion (hard delete: removing
    the row removes the stored key).
    """

    __tablename__ = "custom_provider"
    __table_args__ = (UniqueConstraint("user_id", "provider_id", name="uq_custom_provider_user_provider"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUIDstr = Field(
        sa_column=Column(sa.Uuid(), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    # Lowercase runtime identifier, unique per user, immutable after creation.
    provider_id: str = Field(description="Lowercase runtime identifier, unique per user; immutable after creation")
    # Case-insensitively unique (at the service layer) among the user's active providers.
    display_name: str = Field(description="Editable display label, unique per user ignoring case")
    base_url: str = Field(description="OpenAI-compatible base URL, validated to end in /v1")
    # MUST be stored encrypted; the service encrypts via auth_utils before writing and the
    # Read schema intentionally never exposes this field.
    api_key: str = Field(description="Bearer key. Stored encrypted; never returned in API responses.")
    validation_status: str = Field(
        default=ValidationStatus.DRAFT.value,
        sa_column=Column(sa.String(16), nullable=False, server_default=ValidationStatus.DRAFT.value),
        description="Last endpoint-probe outcome",
    )
    validation_error: str | None = Field(default=None, description="Retained failure message from the last probe")
    last_validated_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    discovered_models: list[dict[str, Any]] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Models discovered from /v1/models (merge semantics; absent ones are retained)",
    )
    manual_models: list[dict[str, Any]] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Hand-entered models, independent of discovery",
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),
    )

    @field_validator("provider_id", "display_name", "api_key")
    @classmethod
    def validate_non_empty(cls, v: str, info: object) -> str:
        return validate_non_empty_string(v, info)


class CustomProviderRead(SQLModel):
    """API representation of a custom provider, never exposing the API key."""

    id: UUID
    user_id: UUID
    provider_id: str
    display_name: str
    base_url: str
    has_api_key: bool = False
    validation_status: str = ValidationStatus.DRAFT.value
    validation_error: str | None = None
    last_validated_at: datetime | None = None
    discovered_models: list[dict[str, Any]] | None = None
    manual_models: list[dict[str, Any]] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
