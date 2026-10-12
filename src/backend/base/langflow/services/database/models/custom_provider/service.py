"""Service layer for user-defined custom model providers.

Owns input validation (provider id / base URL / uniqueness), encrypted
credential round-trips via crud, endpoint probing + model discovery (merge
semantics), validation-status bookkeeping, catalog-entry building for the
unified model system, and the runtime connection resolver used by model
instantiation.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from sqlmodel import func, select

from langflow.services.database.models.custom_provider.crud import (
    _decrypt_api_key,
)
from langflow.services.database.models.custom_provider.crud import (
    create_provider as _create_provider,
)
from langflow.services.database.models.custom_provider.crud import (
    delete_provider as _delete_provider,
)
from langflow.services.database.models.custom_provider.crud import (
    get_provider_by_provider_id as _get_provider_by_provider_id,
)
from langflow.services.database.models.custom_provider.crud import (
    list_providers as _list_providers,
)
from langflow.services.database.models.custom_provider.crud import (
    update_provider as _update_provider,
)
from langflow.services.database.models.custom_provider.discovery import fetch_models
from langflow.services.database.models.custom_provider.model import CustomProvider
from langflow.services.database.models.custom_provider.schemas import ValidationStatus

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

_PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9._-]*$")
MAX_PROVIDER_ID_LEN = 100
MAX_DISPLAY_NAME_LEN = 100
_ICON = "Plug"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_provider_id(value: str) -> str:
    """Validate and return the provider ID (lowercase start, <=100 chars)."""
    stripped = value.strip()
    if not stripped:
        msg = "Provider ID is required"
        raise ValueError(msg)
    if len(stripped) > MAX_PROVIDER_ID_LEN:
        msg = f"Provider ID must be at most {MAX_PROVIDER_ID_LEN} characters"
        raise ValueError(msg)
    if not _PROVIDER_ID_RE.match(stripped):
        msg = "Provider ID must start with a lowercase letter and use only letters, digits, '.', '_', '-'"
        raise ValueError(msg)
    return stripped


def validate_display_name(value: str) -> str:
    """Validate and return the display name."""
    stripped = value.strip()
    if not stripped:
        msg = "Display name is required"
        raise ValueError(msg)
    if len(stripped) > MAX_DISPLAY_NAME_LEN:
        msg = f"Display name must be at most {MAX_DISPLAY_NAME_LEN} characters"
        raise ValueError(msg)
    return stripped


def validate_base_url(value: str) -> str:
    """Validate that *value* is an HTTP(S) URL whose path ends in ``/v1``."""
    stripped = value.strip().rstrip("/")
    from urllib.parse import urlsplit

    parts = urlsplit(stripped)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        msg = "API address must be a valid HTTP(S) URL"
        raise ValueError(msg)
    if not stripped.endswith("/v1"):
        msg = "API address must end with /v1"
        raise ValueError(msg)
    return stripped


def _builtin_provider_ids() -> set[str]:
    """Return provider ids that custom supplier ids must not collide with."""
    from lfx.base.models.provider_registry import get_registry_snapshot, resolve_provider_id
    from lfx.base.models.unified_models.provider_queries import get_model_providers

    ids: set[str] = set(get_registry_snapshot().provider_ids)
    for name in get_model_providers():
        try:
            resolved = resolve_provider_id(name)
        except ValueError:
            resolved = name
        if resolved:
            ids.add(resolved)
    return ids


async def _display_name_taken(
    db: AsyncSession,
    *,
    user_id: UUID | str,
    display_name: str,
    exclude_id: UUID | None = None,
) -> bool:
    stmt = select(CustomProvider).where(
        CustomProvider.user_id == user_id,
        func.lower(CustomProvider.display_name) == display_name.lower(),
    )
    rows = (await db.exec(stmt)).all()
    return any(row.id != exclude_id for row in rows)


# ---------------------------------------------------------------------------
# CRUD orchestration
# ---------------------------------------------------------------------------


async def create_custom_provider(
    db: AsyncSession,
    *,
    user_id: UUID | str,
    provider_id: str,
    display_name: str,
    base_url: str,
    api_key: str,
    discovered_models: list[dict[str, Any]] | None = None,
    manual_models: list[dict[str, Any]] | None = None,
) -> CustomProvider:
    """Validate, uniqueness-check, and create a custom provider (draft status)."""
    pid = validate_provider_id(provider_id)
    name = validate_display_name(display_name)
    url = validate_base_url(base_url)

    if pid in _builtin_provider_ids():
        msg = "Provider ID collides with a built-in provider"
        raise ValueError(msg)
    if await _get_provider_by_provider_id(db, provider_id=pid, user_id=user_id) is not None:
        msg = "A custom provider with this Provider ID already exists"
        raise ValueError(msg)
    if await _display_name_taken(db, user_id=user_id, display_name=name):
        msg = "A custom provider with this display name already exists"
        raise ValueError(msg)

    return await _create_provider(
        db,
        user_id=user_id,
        provider_id=pid,
        display_name=name,
        base_url=url,
        api_key=api_key,
        validation_status=ValidationStatus.DRAFT.value,
        discovered_models=discovered_models or [],
        manual_models=manual_models or [],
    )


async def get_provider(db: AsyncSession, *, provider_id: str, user_id: UUID | str) -> CustomProvider | None:
    return await _get_provider_by_provider_id(db, provider_id=provider_id, user_id=user_id)


async def update_custom_provider(
    db: AsyncSession,
    *,
    provider: CustomProvider,
    display_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> tuple[CustomProvider, bool]:
    """Update a provider. Returns ``(provider, credentials_changed)``.

    ``credentials_changed`` is True when the Base URL or API key changed, in
    which case the caller should re-discover models and revalidate.
    """
    fields: dict[str, Any] = {}
    credentials_changed = False

    if display_name is not None:
        name = validate_display_name(display_name)
        if name.casefold() != provider.display_name.casefold() and await _display_name_taken(
            db, user_id=provider.user_id, display_name=name, exclude_id=provider.id
        ):
            msg = "A custom provider with this display name already exists"
            raise ValueError(msg)
        fields["display_name"] = name

    if base_url is not None:
        url = validate_base_url(base_url)
        if url != provider.base_url:
            fields["base_url"] = url
            credentials_changed = True

    if api_key is not None and api_key.strip():
        fields["api_key"] = api_key
        credentials_changed = True

    if not fields:
        return provider, False

    return await _update_provider(db, provider=provider, **fields), credentials_changed


async def refresh_custom_provider(db: AsyncSession, *, provider: CustomProvider) -> tuple[CustomProvider, str | None]:
    """Probe the endpoint, merge discovered models, update validation status.

    Merge semantics: models absent from this refresh are retained. Returns
    ``(provider, error)`` where ``error`` is ``None`` on success.
    """
    key = _decrypt_api_key(provider.api_key)
    url = provider.base_url
    try:
        new_models: list[dict[str, Any]] = []
        for model_type in ("llm", "embeddings"):
            new_models.extend(_discover_type(url, key, model_type))
        merged = _merge_by_id_and_type(provider.discovered_models or [], new_models)
        return (
            await _update_provider(
                db,
                provider=provider,
                discovered_models=merged,
                validation_status=ValidationStatus.VALID.value,
                validation_error=None,
                last_validated_at=_utcnow(),
            ),
            None,
        )
    except ValueError as e:
        await _update_provider(
            db,
            provider=provider,
            validation_status=ValidationStatus.INVALID.value,
            validation_error=str(e),
        )
        return provider, str(e)


async def add_manual_model(
    db: AsyncSession,
    *,
    provider: CustomProvider,
    model_id: str,
    name: str | None = None,
) -> CustomProvider:
    """Add a hand-entered model (duplicate model IDs rejected)."""
    mid = model_id.strip()
    if not mid:
        msg = "Model ID is required"
        raise ValueError(msg)
    display_name = (name or mid).strip() or mid
    if any(item.get("model_id") == mid for item in provider.manual_models or []):
        msg = f"Model ID {mid!r} already exists in this provider"
        raise ValueError(msg)
    if any(item.get("model_id") == mid for item in provider.discovered_models or []):
        msg = f"Model ID {mid!r} already exists in this provider"
        raise ValueError(msg)
    manual = list(provider.manual_models or [])
    manual.append({"model_id": mid, "name": display_name})
    return await _update_provider(db, provider=provider, manual_models=manual)


async def remove_manual_model(
    db: AsyncSession,
    *,
    provider: CustomProvider,
    model_id: str,
) -> CustomProvider:
    manual = [item for item in provider.manual_models or [] if item.get("model_id") != model_id]
    return await _update_provider(db, provider=provider, manual_models=manual)


async def delete_custom_provider(db: AsyncSession, *, provider: CustomProvider) -> None:
    await _delete_provider(db, provider=provider)


# ---------------------------------------------------------------------------
# Catalog integration (per-user overlay into the unified model system)
# ---------------------------------------------------------------------------


def _row_model_entries(row: CustomProvider) -> list[dict[str, Any]]:
    """Turn a supplier row into ``{"model_name", "metadata"}`` catalog entries."""
    from lfx.base.models.model_metadata import create_model_metadata

    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for entry in row.discovered_models or []:
        mid = (entry.get("model_id") or "").strip()
        model_type = entry.get("model_type") or "llm"
        if not mid or (mid, model_type) in seen:
            continue
        seen.add((mid, model_type))
        metadata: dict[str, Any] = dict(
            create_model_metadata(
                provider=row.provider_id,
                name=mid,
                icon=_ICON,
                model_type=model_type,
                tool_calling=model_type == "llm",
            )
        )
        # Unknown-provider instantiation reads these from metadata; without them
        # saved flows resolve to the generic OpenAI-compatible client anyway, but
        # the fallback explicitly requires the param names.
        if model_type == "llm":
            metadata.update(
                {
                    "model_class": "ChatOpenAI",
                    "model_name_param": "model",
                    "api_key_param": "api_key",
                }
            )
        else:
            metadata.update(
                {
                    "embedding_class": "OpenAIEmbeddings",
                    "param_mapping": {"model": "model", "api_key": "api_key"},
                }
            )
        entries.append({"model_name": mid, "metadata": metadata})
    for item in row.manual_models or []:
        mid = (item.get("model_id") or "").strip()
        if not mid or (mid, "llm") in seen:
            continue
        seen.add((mid, "llm"))
        metadata = dict(
            create_model_metadata(
                provider=row.provider_id,
                name=mid,
                icon=_ICON,
                model_type="llm",
                tool_calling=True,
            )
        )
        metadata.update(
            {
                "model_class": "ChatOpenAI",
                "model_name_param": "model",
                "api_key_param": "api_key",
            }
        )
        entries.append({"model_name": mid, "metadata": metadata})
    return entries


async def build_catalog_entries(db: AsyncSession, *, user_id: UUID | str) -> list[dict[str, Any]]:
    """Return catalog-shaped provider entries for every active supplier of *user_id*."""
    rows = await _list_providers(db, user_id=user_id)
    entries: list[dict[str, Any]] = []
    for row in rows:
        models = _row_model_entries(row)
        entries.append(
            {
                "provider": row.provider_id,
                "provider_id": row.provider_id,
                "display_name": row.display_name,
                "icon": _ICON,
                "custom": True,
                "is_configured": True,
                "live_discovery": True,
                "is_enabled": bool(models),
                "models": models,
                "num_models": len(models),
            }
        )
    return entries


async def build_catalog_entries_for_user(user_id: UUID | str) -> list[dict[str, Any]]:
    """Session-wrapped variant for lfx callers that have no injected session."""
    from langflow.services.deps import session_scope

    async with session_scope() as session:
        return await build_catalog_entries(session, user_id=user_id)


async def get_custom_provider_ids(db: AsyncSession, *, user_id: UUID | str) -> list[str]:
    """Return the provider ids of every active supplier (for configured/enabled seams)."""
    rows = await _list_providers(db, user_id=user_id)
    return [row.provider_id for row in rows]


# ---------------------------------------------------------------------------
# Endpoint preview (no persistence) and small helpers
# ---------------------------------------------------------------------------


def preview_models(base_url: str, api_key: str | None) -> dict[str, list[str]]:
    """Fetch model ids once and return them for both model types."""
    names = fetch_models(base_url, api_key)
    return {"llm": names, "embeddings": names}


def _discover_type(base_url: str, api_key: str | None, model_type: str) -> list[dict[str, Any]]:
    from langflow.services.database.models.custom_provider.discovery import to_stored_models

    return to_stored_models(base_url, api_key, model_type=model_type)


def _merge_by_id_and_type(existing: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = {(e.get("model_id"), e.get("model_type")) for e in existing}
    merged = list(existing)
    for entry in new:
        key = (entry.get("model_id"), entry.get("model_type"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(entry)
    return merged


def _utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Runtime connection resolver (used by lfx model instantiation)
# ---------------------------------------------------------------------------


def get_custom_provider_connection(user_id: UUID | str | None, provider_id: str) -> dict[str, Any] | None:
    """Resolve a supplier's connection for a flow run, or ``None`` when absent.

    Used by lfx instantiation for a ``(provider_id, model_name)`` pair whose
    provider is a custom supplier. Returns the decrypted ``base_url`` and
    ``api_key``; ``None`` means "provider deleted / unavailable".
    """
    if user_id is None or (isinstance(user_id, str) and user_id == "None"):
        return None
    from lfx.utils.async_helpers import run_until_complete

    return run_until_complete(_get_connection(user_id, provider_id))


async def _get_connection(user_id: UUID | str, provider_id: str) -> dict[str, Any] | None:
    from langflow.services.deps import session_scope

    async with session_scope() as session:
        row = await _get_provider_by_provider_id(session, provider_id=provider_id, user_id=user_id)
        if row is None:
            return None
        return {
            "provider_id": row.provider_id,
            "display_name": row.display_name,
            "base_url": row.base_url,
            "api_key": _decrypt_api_key(row.api_key),
        }
