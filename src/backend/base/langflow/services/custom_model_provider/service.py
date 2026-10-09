from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from cryptography.fernet import InvalidToken
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from langflow.services.auth import utils as auth_utils
from langflow.services.database.models.custom_model_provider import (
    CustomModelProvider,
    CustomModelProviderModel,
    CustomModelProviderModelRead,
    CustomModelProviderRead,
    normalize_provider_name,
)
from langflow.services.database.utils import parse_uuid

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession


class CustomProviderCredentialError(RuntimeError):
    """Raised when provider credential material cannot be safely used."""


_DEFAULT_PORTS = {"http": 80, "https": 443}


def _required(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        msg = f"{field_name} must not be empty"
        raise ValueError(msg)
    return stripped


def normalize_base_url(value: str) -> str:
    """Validate and canonicalize an HTTP(S) API root without changing its path."""
    raw = _required(value, "base_url")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        msg = "base_url must be an absolute HTTP or HTTPS URL"
        raise ValueError(msg)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        msg = "base_url must not contain credentials, a query, or a fragment"
        raise ValueError(msg)
    try:
        port = parsed.port
    except ValueError as exc:
        msg = "base_url contains an invalid port"
        raise ValueError(msg) from exc
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    if ":" in host:
        host = f"[{host}]"
    default_port = port == _DEFAULT_PORTS[parsed.scheme]
    netloc = host if port is None or default_port else f"{host}:{port}"
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def _encrypt_api_key(api_key: str) -> str:
    value = _required(api_key, "api_key")
    try:
        return auth_utils.encrypt_api_key(value)
    except (ValueError, InvalidToken, TypeError, AttributeError) as exc:
        msg = "Failed to encrypt custom provider API key"
        raise CustomProviderCredentialError(msg) from exc


def to_read(provider: CustomModelProvider) -> CustomModelProviderRead:
    """Build the public representation without exposing encrypted credential material."""
    if provider.created_at is None or provider.updated_at is None:
        msg = "Persisted custom provider is missing timestamps"
        raise RuntimeError(msg)
    return CustomModelProviderRead(
        id=provider.id,
        name=provider.name,
        base_url=provider.base_url,
        has_api_key=bool(provider.api_key),
        is_verified=provider.is_verified,
        verification_error=provider.verification_error,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


async def get_provider(
    db: AsyncSession,
    *,
    provider_id: UUID | str,
    user_id: UUID | str,
    include_deleted: bool = False,
) -> CustomModelProvider | None:
    stmt = select(CustomModelProvider).where(
        CustomModelProvider.id == parse_uuid(provider_id, field_name="provider_id"),
        CustomModelProvider.user_id == parse_uuid(user_id, field_name="user_id"),
    )
    if not include_deleted:
        stmt = stmt.where(CustomModelProvider.deleted_at.is_(None))
    return (await db.exec(stmt)).first()


async def list_providers(db: AsyncSession, *, user_id: UUID | str) -> list[CustomModelProvider]:
    stmt = (
        select(CustomModelProvider)
        .where(
            CustomModelProvider.user_id == parse_uuid(user_id, field_name="user_id"),
            CustomModelProvider.deleted_at.is_(None),
        )
        .order_by(col(CustomModelProvider.created_at).desc())
    )
    return list((await db.exec(stmt)).all())


async def create_provider(
    db: AsyncSession,
    *,
    user_id: UUID | str,
    name: str,
    base_url: str,
    api_key: str,
) -> CustomModelProvider:
    now = datetime.now(timezone.utc)
    provider = CustomModelProvider(
        user_id=parse_uuid(user_id, field_name="user_id"),
        name=_required(name, "name"),
        normalized_name=normalize_provider_name(name),
        base_url=normalize_base_url(base_url),
        api_key=_encrypt_api_key(api_key),
        created_at=now,
        updated_at=now,
    )
    db.add(provider)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        msg = "An active custom provider with this name already exists"
        raise ValueError(msg) from exc
    await db.refresh(provider)
    return provider


async def update_provider(
    db: AsyncSession,
    *,
    provider: CustomModelProvider,
    user_id: UUID | str,
    name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> CustomModelProvider:
    if provider.user_id != parse_uuid(user_id, field_name="user_id") or provider.deleted_at is not None:
        msg = "Custom provider not found"
        raise LookupError(msg)
    if name is not None:
        provider.name = _required(name, "name")
        provider.normalized_name = normalize_provider_name(provider.name)
    if base_url is not None:
        provider.base_url = normalize_base_url(base_url)
    if api_key is not None:
        provider.api_key = _encrypt_api_key(api_key)
    provider.updated_at = datetime.now(timezone.utc)
    db.add(provider)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        msg = "An active custom provider with this name already exists"
        raise ValueError(msg) from exc
    await db.refresh(provider)
    return provider


def get_provider_api_key(provider: CustomModelProvider) -> str:
    if provider.deleted_at is not None or not provider.api_key:
        msg = "Custom provider API key is unavailable"
        raise CustomProviderCredentialError(msg)
    try:
        decrypted = auth_utils.decrypt_api_key(provider.api_key)
    except (ValueError, InvalidToken, TypeError, AttributeError) as exc:
        msg = "Failed to decrypt custom provider API key"
        raise CustomProviderCredentialError(msg) from exc
    if not decrypted:
        msg = "Failed to decrypt custom provider API key"
        raise CustomProviderCredentialError(msg)
    return decrypted


async def soft_delete_provider(
    db: AsyncSession,
    *,
    provider: CustomModelProvider,
    user_id: UUID | str,
) -> None:
    if provider.user_id != parse_uuid(user_id, field_name="user_id") or provider.deleted_at is not None:
        msg = "Custom provider not found"
        raise LookupError(msg)
    provider.soft_delete()
    provider.updated_at = provider.deleted_at
    db.add(provider)
    await db.flush()


async def verify_provider(db: AsyncSession, *, provider: CustomModelProvider) -> list[str]:
    """Probe model discovery and persist the result without rejecting provider storage."""
    from .client import ModelDiscoveryError, discover_model_ids

    try:
        model_ids = await asyncio.to_thread(discover_model_ids, provider.base_url, get_provider_api_key(provider))
    except (CustomProviderCredentialError, ModelDiscoveryError) as exc:
        provider.is_verified = False
        provider.verification_error = str(exc)[:2000]
        model_ids = []
    else:
        provider.is_verified = True
        provider.verification_error = None
    provider.updated_at = datetime.now(timezone.utc)
    db.add(provider)
    await db.flush()
    await db.refresh(provider)
    return model_ids


def model_to_read(model: CustomModelProviderModel) -> CustomModelProviderModelRead:
    return CustomModelProviderModelRead.model_validate(model)


async def resolve_provider_model_reference(
    db: AsyncSession,
    *,
    provider_id: UUID | str,
    user_id: UUID | str,
    model_id: str,
) -> tuple[CustomModelProvider | None, CustomModelProviderModel | None]:
    """Resolve a persisted reference without hiding deleted-provider diagnostics."""
    provider = await get_provider(db, provider_id=provider_id, user_id=user_id, include_deleted=True)
    if provider is None:
        return None, None
    stmt = select(CustomModelProviderModel).where(
        CustomModelProviderModel.provider_id == provider.id,
        CustomModelProviderModel.model_id == _required(model_id, "model_id"),
    )
    return provider, (await db.exec(stmt)).first()


async def list_models(
    db: AsyncSession,
    *,
    provider: CustomModelProvider,
    user_id: UUID | str,
    include_unavailable: bool = True,
) -> list[CustomModelProviderModel]:
    if provider.user_id != parse_uuid(user_id, field_name="user_id"):
        msg = "Custom provider not found"
        raise LookupError(msg)
    stmt = (
        select(CustomModelProviderModel)
        .where(CustomModelProviderModel.provider_id == provider.id)
        .order_by(col(CustomModelProviderModel.model_id))
    )
    if not include_unavailable:
        stmt = stmt.where(CustomModelProviderModel.available.is_(True))
    return list((await db.exec(stmt)).all())


async def refresh_provider_models(
    db: AsyncSession,
    *,
    provider: CustomModelProvider,
    user_id: UUID | str,
) -> list[CustomModelProviderModel]:
    from .client import ModelDiscoveryError, discover_model_ids

    user_uuid = parse_uuid(user_id, field_name="user_id")
    if provider.user_id != user_uuid or provider.deleted_at is not None:
        msg = "Custom provider not found"
        raise LookupError(msg)
    expected_updated_at = provider.updated_at
    try:
        discovered_ids = await asyncio.to_thread(
            discover_model_ids,
            provider.base_url,
            get_provider_api_key(provider),
        )
    except (CustomProviderCredentialError, ModelDiscoveryError) as exc:
        provider.is_verified = False
        provider.verification_error = str(exc)[:2000]
        provider.updated_at = datetime.now(timezone.utc)
        db.add(provider)
        await db.flush()
        await db.refresh(provider)
        return await list_models(db, provider=provider, user_id=user_uuid)

    await db.refresh(provider)
    if provider.deleted_at is not None or provider.updated_at != expected_updated_at:
        msg = "Custom provider changed while model discovery was running"
        raise RuntimeError(msg)

    now = datetime.now(timezone.utc)
    existing = {model.model_id: model for model in await list_models(db, provider=provider, user_id=user_uuid)}
    discovered_set = set(discovered_ids)
    for model_id, model in existing.items():
        model.discovered = model_id in discovered_set
        model.available = model.discovered or model.manually_added
        if model.discovered:
            model.last_discovered_at = now
        model.updated_at = now
        db.add(model)
    for model_id in discovered_set - existing.keys():
        db.add(
            CustomModelProviderModel(
                provider_id=provider.id,
                model_id=model_id,
                discovered=True,
                available=True,
                last_discovered_at=now,
                created_at=now,
                updated_at=now,
            )
        )
    provider.is_verified = True
    provider.verification_error = None
    provider.updated_at = now
    db.add(provider)
    await db.flush()
    await db.refresh(provider)
    return await list_models(db, provider=provider, user_id=user_uuid)


async def add_manual_model(
    db: AsyncSession,
    *,
    provider: CustomModelProvider,
    user_id: UUID | str,
    model_id: str,
) -> CustomModelProviderModel:
    user_uuid = parse_uuid(user_id, field_name="user_id")
    if provider.user_id != user_uuid or provider.deleted_at is not None:
        msg = "Custom provider not found"
        raise LookupError(msg)
    normalized_id = _required(model_id, "model_id")
    stmt = select(CustomModelProviderModel).where(
        CustomModelProviderModel.provider_id == provider.id,
        CustomModelProviderModel.model_id == normalized_id,
    )
    model = (await db.exec(stmt)).first()
    now = datetime.now(timezone.utc)
    if model is None:
        model = CustomModelProviderModel(
            provider_id=provider.id,
            model_id=normalized_id,
            manually_added=True,
            available=True,
            created_at=now,
            updated_at=now,
        )
    else:
        model.manually_added = True
        model.available = True
        model.updated_at = now
    db.add(model)
    await db.flush()
    await db.refresh(model)
    return model


async def remove_manual_model(
    db: AsyncSession,
    *,
    provider: CustomModelProvider,
    user_id: UUID | str,
    model_id: str,
) -> CustomModelProviderModel | None:
    user_uuid = parse_uuid(user_id, field_name="user_id")
    if provider.user_id != user_uuid or provider.deleted_at is not None:
        msg = "Custom provider not found"
        raise LookupError(msg)
    stmt = select(CustomModelProviderModel).where(
        CustomModelProviderModel.provider_id == provider.id,
        CustomModelProviderModel.model_id == _required(model_id, "model_id"),
    )
    model = (await db.exec(stmt)).first()
    if model is None or not model.manually_added:
        return None
    model.manually_added = False
    model.available = model.discovered
    model.updated_at = datetime.now(timezone.utc)
    db.add(model)
    await db.flush()
    await db.refresh(model)
    return model
