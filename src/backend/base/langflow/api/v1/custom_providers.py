from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.services.authorization.guards import ensure_permission
from langflow.services.database.models.custom_provider.crud import provider_read
from langflow.services.database.models.custom_provider.model import CustomProvider
from langflow.services.database.models.custom_provider.service import (
    add_manual_model as service_add_manual_model,
)
from langflow.services.database.models.custom_provider.service import (
    build_catalog_entries,
    create_custom_provider,
    get_custom_provider_ids,
    preview_models,
    refresh_custom_provider,
    update_custom_provider,
)
from langflow.services.database.models.custom_provider.service import (
    delete_custom_provider as service_delete_custom_provider,
)
from langflow.services.database.models.custom_provider.service import (
    remove_manual_model as service_remove_manual_model,
)

router = APIRouter(prefix="/custom-providers", tags=["Custom Providers"])


class CustomProviderCreate(BaseModel):
    provider_id: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=100)
    base_url: str
    api_key: str
    discovered_models: list[dict[str, Any]] = []
    manual_models: list[dict[str, Any]] = []


class CustomProviderUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    base_url: str | None = None
    api_key: str | None = None


class PreviewRequest(BaseModel):
    base_url: str
    api_key: str


class PreviewResponse(BaseModel):
    valid: bool
    error: str | None = None
    models: dict[str, list[str]] = {"llm": [], "embeddings": []}


class ManualModelRequest(BaseModel):
    model_id: str = Field(min_length=1)
    name: str | None = None


async def _get_owned_provider(
    session: DbSession,
    current_user: CurrentActiveUser,
    provider_id: str,
    *,
    act: str,
) -> CustomProvider:
    from langflow.services.database.models.custom_provider.service import get_provider

    provider = await get_provider(session, provider_id=provider_id, user_id=current_user.id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Custom provider not found")
    # Owner scope is enforced by every query above; this is the same audited
    # write-permission guard other per-resource routes use (no-op when RBAC off).
    await ensure_permission(current_user, domain="*", obj=f"custom_provider:{provider.id}", act=act)
    return provider


@router.get("", response_model=list[dict[str, Any]])
async def list_custom_providers(
    *,
    session: DbSession,
    current_user: CurrentActiveUser,
    search: Annotated[str | None, Query()] = None,
) -> list[dict[str, Any]]:
    """List the current user's custom providers, newest first, optionally filtered."""
    providers = await _list_owned(session, current_user.id)
    if search:
        needle = search.casefold()
        providers = [p for p in providers if needle in p.display_name.casefold() or needle in p.provider_id.casefold()]
    return [provider_read(p) for p in providers]


async def _list_owned(session: DbSession, user_id) -> list[CustomProvider]:
    from langflow.services.database.models.custom_provider.crud import list_providers

    return await list_providers(session, user_id=user_id)


@router.get("/catalog", response_model=list[dict[str, Any]])
async def get_custom_provider_catalog(
    *,
    session: DbSession,
    current_user: CurrentActiveUser,
) -> list[dict[str, Any]]:
    """Return catalog-shaped entries (used to overlay suppliers into model lists)."""
    return await build_catalog_entries(session, user_id=current_user.id)


@router.get("/provider-ids", response_model=list[str])
async def list_custom_provider_ids(
    *,
    session: DbSession,
    current_user: CurrentActiveUser,
) -> list[str]:
    """Return every active custom provider id (configured/enabled seams)."""
    return await get_custom_provider_ids(session, user_id=current_user.id)


@router.get("/{provider_id}", response_model=dict[str, Any])
async def get_custom_provider(
    *,
    session: DbSession,
    current_user: CurrentActiveUser,
    provider_id: str,
) -> dict[str, Any]:
    provider = await _get_owned_provider(session, current_user, provider_id, act="read")
    return provider_read(provider)


@router.post("", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
async def post_custom_provider(
    *,
    session: DbSession,
    current_user: CurrentActiveUser,
    payload: CustomProviderCreate,
) -> dict[str, Any]:
    await ensure_permission(current_user, domain="*", obj="custom_provider:*", act="create")
    try:
        provider = await create_custom_provider(
            session,
            user_id=current_user.id,
            provider_id=payload.provider_id,
            display_name=payload.display_name,
            base_url=payload.base_url,
            api_key=payload.api_key,
            discovered_models=payload.discovered_models,
            manual_models=payload.manual_models,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await session.commit()
    await session.refresh(provider)
    return provider_read(provider)


@router.patch("/{provider_id}", response_model=dict[str, Any])
async def patch_custom_provider(
    *,
    session: DbSession,
    current_user: CurrentActiveUser,
    provider_id: str,
    payload: CustomProviderUpdate,
) -> dict[str, Any]:
    provider = await _get_owned_provider(session, current_user, provider_id, act="write")
    try:
        updated, credentials_changed = await update_custom_provider(
            session,
            provider=provider,
            display_name=payload.display_name,
            base_url=payload.base_url,
            api_key=payload.api_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if credentials_changed:
        # URL or key changed: rediscover + revalidate (merge semantics).
        updated, error = await refresh_custom_provider(session, provider=updated)
        if error:
            raise HTTPException(status_code=400, detail=error)
    await session.commit()
    await session.refresh(updated)
    return provider_read(updated)


@router.post("/{provider_id}/refresh", response_model=dict[str, Any])
async def post_custom_provider_refresh(
    *,
    session: DbSession,
    current_user: CurrentActiveUser,
    provider_id: str,
) -> dict[str, Any]:
    provider = await _get_owned_provider(session, current_user, provider_id, act="write")
    updated, error = await refresh_custom_provider(session, provider=provider)
    await session.commit()
    await session.refresh(updated)
    result = provider_read(updated)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return result


@router.post("/{provider_id}/models", response_model=dict[str, Any])
async def post_custom_provider_manual_model(
    *,
    session: DbSession,
    current_user: CurrentActiveUser,
    provider_id: str,
    payload: ManualModelRequest,
) -> dict[str, Any]:
    provider = await _get_owned_provider(session, current_user, provider_id, act="write")
    try:
        updated = await service_add_manual_model(
            session, provider=provider, model_id=payload.model_id, name=payload.name
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await session.commit()
    await session.refresh(updated)
    return provider_read(updated)


@router.delete("/{provider_id}/models/{model_id}", response_model=dict[str, Any])
async def delete_custom_provider_manual_model(
    *,
    session: DbSession,
    current_user: CurrentActiveUser,
    provider_id: str,
    model_id: str,
) -> dict[str, Any]:
    provider = await _get_owned_provider(session, current_user, provider_id, act="write")
    updated = await service_remove_manual_model(session, provider=provider, model_id=model_id)
    await session.commit()
    await session.refresh(updated)
    return provider_read(updated)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_provider(
    *,
    session: DbSession,
    current_user: CurrentActiveUser,
    provider_id: str,
) -> None:
    provider = await _get_owned_provider(session, current_user, provider_id, act="delete")
    await service_delete_custom_provider(session, provider=provider)
    await session.commit()


@router.post("/meta/preview", response_model=PreviewResponse)
async def post_custom_provider_preview(
    *,
    current_user: CurrentActiveUser,
    payload: PreviewRequest,
) -> PreviewResponse:
    """Probe a Base URL + key and return the endpoint's model ids (no persistence)."""
    # Declared after path routes so /meta/preview cannot shadow /{provider_id}.
    await ensure_permission(current_user, domain="*", obj="custom_provider:*", act="create")
    try:
        models = preview_models(payload.base_url, payload.api_key)
    except ValueError as e:
        return PreviewResponse(valid=False, error=str(e))
    return PreviewResponse(valid=True, models=models)
