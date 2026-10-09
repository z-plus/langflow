import unicodedata
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import sqlalchemy as sa
from pydantic import field_validator, model_validator
from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlmodel import Column, DateTime, Field, Relationship, SQLModel, func

from langflow.schema.serialize import UUIDstr

if TYPE_CHECKING:
    from langflow.services.database.models.user.model import User


def normalize_provider_name(value: str) -> str:
    return unicodedata.normalize("NFKC", value.strip()).casefold()


class CustomModelProvider(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "custom_model_provider"
    __table_args__ = (
        Index(
            "uq_custom_model_provider_active_name",
            "user_id",
            "normalized_name",
            unique=True,
            sqlite_where=sa.text("deleted_at IS NULL"),
            postgresql_where=sa.text("deleted_at IS NULL"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUIDstr = Field(
        sa_column=Column(sa.Uuid(), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    name: str = Field(min_length=1, max_length=200)
    normalized_name: str = Field(max_length=200)
    base_url: str = Field(max_length=2048)
    api_key: str | None = Field(default=None, description="Encrypted API key; never serialize this field.")
    is_verified: bool = Field(default=False, nullable=False)
    verification_error: str | None = Field(default=None, max_length=2000)
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),
    )
    deleted_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))

    user: "User" = Relationship(back_populates="custom_model_providers")
    models: list["CustomModelProviderModel"] = Relationship(
        back_populates="provider",
        sa_relationship_kwargs={"cascade": "all, delete, delete-orphan"},
    )

    @field_validator("name", "base_url")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            msg = "Value cannot be empty"
            raise ValueError(msg)
        return stripped

    @model_validator(mode="after")
    def set_normalized_name(self) -> "CustomModelProvider":
        self.normalized_name = normalize_provider_name(self.name)
        return self

    def soft_delete(self) -> None:
        self.api_key = None
        self.deleted_at = datetime.now(timezone.utc)
        self.is_verified = False


class CustomModelProviderModel(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "custom_model_provider_model"
    __table_args__ = (UniqueConstraint("provider_id", "model_id", name="uq_custom_model_provider_model_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    provider_id: UUID = Field(
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("custom_model_provider.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    model_id: str = Field(min_length=1, max_length=200)
    manually_added: bool = Field(default=False, nullable=False)
    discovered: bool = Field(default=False, nullable=False)
    available: bool = Field(default=True, nullable=False)
    last_discovered_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),
    )

    provider: CustomModelProvider = Relationship(back_populates="models")

    @field_validator("model_id")
    @classmethod
    def normalize_model_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            msg = "Model ID cannot be empty"
            raise ValueError(msg)
        return stripped


class CustomModelProviderRead(SQLModel):
    id: UUID
    name: str
    base_url: str
    has_api_key: bool
    is_verified: bool
    verification_error: str | None
    created_at: datetime
    updated_at: datetime


class CustomModelProviderModelRead(SQLModel):
    id: UUID
    model_id: str
    manually_added: bool
    discovered: bool
    available: bool
    last_discovered_at: datetime | None
