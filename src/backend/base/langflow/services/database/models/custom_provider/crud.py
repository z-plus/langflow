from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cryptography.fernet import InvalidToken
from lfx.log.logger import logger
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from langflow.services.auth import utils as auth_utils
from langflow.services.database.models.custom_provider.model import CustomProvider
from langflow.services.database.utils import parse_uuid

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession


def _strip_or_raise(value: str, field_name: str) -> str:
    """Return *value* stripped of whitespace, or raise if blank."""
    stripped = value.strip()
    if not stripped:
        msg = f"{field_name} must not be empty"
        raise ValueError(msg)
    return stripped


def _encrypt_api_key(raw: str) -> str:
    """Encrypt an API key, raising ``RuntimeError`` on failure."""
    stripped = _strip_or_raise(raw, "api_key")
    try:
        return auth_utils.encrypt_api_key(stripped)
    except (ValueError, InvalidToken, TypeError, AttributeError) as e:
        msg = "Failed to encrypt API key -- check server encryption configuration"
        raise RuntimeError(msg) from e


def _decrypt_api_key(encrypted: str) -> str | None:
    """Decrypt a stored API key, returning ``None`` when it cannot be decrypted."""
    try:
        return auth_utils.decrypt_api_key(encrypted)
    except (ValueError, InvalidToken, TypeError, AttributeError) as exc:
        logger.warning("Failed to decrypt custom provider API key: %s", exc)
        return None


async def get_provider_by_id(
    db: AsyncSession,
    *,
    provider_row_id: UUID | str,
    user_id: UUID | str,
) -> CustomProvider | None:
    """Load a custom provider row for *user_id* by its row id."""
    row_uuid = parse_uuid(provider_row_id, field_name="provider_id")
    user_uuid = parse_uuid(user_id, field_name="user_id")
    stmt = select(CustomProvider).where(
        CustomProvider.id == row_uuid,
        CustomProvider.user_id == user_uuid,
    )
    return (await db.exec(stmt)).first()


async def get_provider_by_provider_id(
    db: AsyncSession,
    *,
    provider_id: str,
    user_id: UUID | str,
) -> CustomProvider | None:
    """Load a custom provider row by its runtime identity for *user_id*."""
    user_uuid = parse_uuid(user_id, field_name="user_id")
    stmt = select(CustomProvider).where(
        CustomProvider.provider_id == provider_id,
        CustomProvider.user_id == user_uuid,
    )
    return (await db.exec(stmt)).first()


async def list_providers(db: AsyncSession, *, user_id: UUID | str) -> list[CustomProvider]:
    """Return every custom provider owned by *user_id*, newest first."""
    user_uuid = parse_uuid(user_id, field_name="user_id")
    stmt = select(CustomProvider).where(CustomProvider.user_id == user_uuid).order_by(CustomProvider.created_at.desc())
    return list((await db.exec(stmt)).all())


async def _flush_or_integrity(db: AsyncSession, context: str) -> None:
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        await logger.aerror("IntegrityError %s", context)
        msg = "Custom provider conflicts with an existing record"
        raise ValueError(msg) from exc


async def create_provider(
    db: AsyncSession,
    *,
    user_id: UUID | str,
    provider_id: str,
    display_name: str,
    base_url: str,
    api_key: str,
    **extra: Any,
) -> CustomProvider:
    """Create and flush a custom provider row with an encrypted key."""
    provider = CustomProvider(
        user_id=parse_uuid(user_id, field_name="user_id"),
        provider_id=_strip_or_raise(provider_id, "provider_id"),
        display_name=_strip_or_raise(display_name, "display_name"),
        base_url=_strip_or_raise(base_url, "base_url"),
        api_key=_encrypt_api_key(api_key),
        **extra,
    )
    db.add(provider)
    await _flush_or_integrity(db, f"creating custom provider {provider_id!r}")
    await db.refresh(provider)
    return provider


async def update_provider(db: AsyncSession, *, provider: CustomProvider, **fields: Any) -> CustomProvider:
    """Apply *fields* to an already-loaded provider row and flush."""
    for key, value in fields.items():
        if key == "api_key" and value is not None:
            provider.api_key = _encrypt_api_key(value)
        else:
            setattr(provider, key, value)
    await _flush_or_integrity(db, f"updating custom provider {provider.provider_id!r}")
    await db.refresh(provider)
    return provider


async def delete_provider(db: AsyncSession, *, provider: CustomProvider) -> None:
    """Hard-delete a custom provider row (removes the encrypted key with it)."""
    await db.delete(provider)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        await logger.aerror("Failed to delete custom provider id=%s", provider.id)
        msg = f"Failed to delete custom provider id={provider.id}"
        raise ValueError(msg) from exc


def provider_read(provider: CustomProvider) -> dict[str, Any]:
    """Serialize a provider row for API responses (never the key)."""
    return {
        "id": provider.id,
        "user_id": provider.user_id,
        "provider_id": provider.provider_id,
        "display_name": provider.display_name,
        "base_url": provider.base_url,
        "has_api_key": bool(provider.api_key),
        "validation_status": provider.validation_status,
        "validation_error": provider.validation_error,
        "last_validated_at": provider.last_validated_at,
        "discovered_models": provider.discovered_models or [],
        "manual_models": provider.manual_models or [],
        "created_at": provider.created_at,
        "updated_at": provider.updated_at,
    }
