from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from lfx.services.model_provider_policy import (
    ModelProviderPolicyError,
    ModelProviderPolicyPurpose,
    ModelProviderPolicySnapshot,
    aresolve_model_provider_policy,
)
from pydantic import BaseModel, Field, field_validator

from langflow.api.utils import DbSession, DbSessionReadOnly
from langflow.api.v1.model_provider_policy_scope import (
    ProviderPolicyAttributes,
    ProviderPolicyAttributesDependency,
)
from langflow.services.auth.utils import get_current_active_user
from langflow.services.custom_model_provider import (
    add_manual_model,
    create_provider,
    custom_provider_identity,
    get_provider,
    list_models,
    list_providers,
    model_to_read,
    normalize_base_url,
    refresh_provider_models,
    remove_manual_model,
    soft_delete_provider,
    to_read,
    update_provider,
)
from langflow.services.database.models.custom_model_provider import (
    CustomModelProviderModelRead,
    CustomModelProviderRead,
)
from langflow.services.database.models.user.model import User

router = APIRouter(prefix="/models/custom-providers", tags=["Models"], include_in_schema=False)


def _non_empty(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        msg = f"{field_name} must not be empty"
        raise ValueError(msg)
    return stripped


class CustomModelProviderCreate(BaseModel):
    name: str = Field(max_length=200)
    base_url: str = Field(max_length=2048)
    api_key: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _non_empty(value, "name")

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return normalize_base_url(value)

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str) -> str:
        return _non_empty(value, "api_key")


class CustomModelProviderUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            msg = "name must not be null"
            raise ValueError(msg)
        return _non_empty(value, "name")

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None:
            msg = "base_url must not be null"
            raise ValueError(msg)
        return normalize_base_url(value)

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str | None) -> str | None:
        if value is None:
            msg = "api_key must not be null"
            raise ValueError(msg)
        return _non_empty(value, "api_key")


class CustomModelProviderModelCreate(BaseModel):
    model_id: str = Field(max_length=200)

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        return _non_empty(value, "model_id")


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom provider not found")


def _conflict(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


async def _provider_policy(
    current_user: User,
    provider_ids: list[str],
    purpose: ModelProviderPolicyPurpose,
    attributes: ProviderPolicyAttributes,
) -> ModelProviderPolicySnapshot:
    return await aresolve_model_provider_policy(
        user_id=current_user.id,
        providers=provider_ids,
        purpose=purpose,
        attributes=attributes,
    )


async def _require_provider_policy(
    current_user: User,
    provider_id: UUID,
    purpose: ModelProviderPolicyPurpose,
    attributes: ProviderPolicyAttributes,
) -> None:
    try:
        (await _provider_policy(current_user, [custom_provider_identity(provider_id)], purpose, attributes)).require(
            custom_provider_identity(provider_id)
        )
    except ModelProviderPolicyError as exc:
        raise _not_found() from exc


@router.get("", response_model=list[CustomModelProviderRead])
async def list_custom_model_providers(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: DbSessionReadOnly,
    provider_policy_attributes: ProviderPolicyAttributesDependency,
) -> list[CustomModelProviderRead]:
    providers = await list_providers(session, user_id=current_user.id)
    policy = await _provider_policy(
        current_user,
        [custom_provider_identity(provider.id) for provider in providers],
        ModelProviderPolicyPurpose.DISCOVER,
        provider_policy_attributes,
    )
    return [to_read(provider) for provider in providers if policy.allows(custom_provider_identity(provider.id))]


@router.post("", response_model=CustomModelProviderRead, status_code=status.HTTP_201_CREATED)
async def create_custom_model_provider(
    payload: CustomModelProviderCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: DbSession,
    provider_policy_attributes: ProviderPolicyAttributesDependency,
) -> CustomModelProviderRead:
    try:
        provider = await create_provider(session, user_id=current_user.id, **payload.model_dump())
    except ValueError as exc:
        raise _conflict(exc) from exc
    await _require_provider_policy(
        current_user, provider.id, ModelProviderPolicyPurpose.CONFIGURE, provider_policy_attributes
    )
    await refresh_provider_models(session, provider=provider, user_id=current_user.id)
    return to_read(provider)


@router.get("/{provider_id}", response_model=CustomModelProviderRead)
async def read_custom_model_provider(
    provider_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: DbSessionReadOnly,
    provider_policy_attributes: ProviderPolicyAttributesDependency,
) -> CustomModelProviderRead:
    provider = await get_provider(session, provider_id=provider_id, user_id=current_user.id)
    if provider is None:
        raise _not_found()
    await _require_provider_policy(
        current_user, provider.id, ModelProviderPolicyPurpose.DISCOVER, provider_policy_attributes
    )
    return to_read(provider)


@router.patch("/{provider_id}", response_model=CustomModelProviderRead)
async def update_custom_model_provider(
    provider_id: UUID,
    payload: CustomModelProviderUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: DbSession,
    provider_policy_attributes: ProviderPolicyAttributesDependency,
) -> CustomModelProviderRead:
    provider = await get_provider(session, provider_id=provider_id, user_id=current_user.id)
    if provider is None:
        raise _not_found()
    await _require_provider_policy(
        current_user, provider.id, ModelProviderPolicyPurpose.CONFIGURE, provider_policy_attributes
    )
    try:
        updated = await update_provider(
            session,
            provider=provider,
            user_id=current_user.id,
            **payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise _conflict(exc) from exc
    if payload.base_url is not None or payload.api_key is not None:
        await refresh_provider_models(session, provider=updated, user_id=current_user.id)
    return to_read(updated)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_model_provider(
    provider_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: DbSession,
    provider_policy_attributes: ProviderPolicyAttributesDependency,
) -> Response:
    provider = await get_provider(session, provider_id=provider_id, user_id=current_user.id)
    if provider is None:
        raise _not_found()
    await _require_provider_policy(
        current_user, provider.id, ModelProviderPolicyPurpose.CONFIGURE, provider_policy_attributes
    )
    await soft_delete_provider(session, provider=provider, user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{provider_id}/models", response_model=list[CustomModelProviderModelRead])
async def list_custom_provider_models(
    provider_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: DbSessionReadOnly,
    provider_policy_attributes: ProviderPolicyAttributesDependency,
) -> list[CustomModelProviderModelRead]:
    provider = await get_provider(session, provider_id=provider_id, user_id=current_user.id)
    if provider is None:
        raise _not_found()
    await _require_provider_policy(
        current_user, provider.id, ModelProviderPolicyPurpose.DISCOVER, provider_policy_attributes
    )
    models = await list_models(session, provider=provider, user_id=current_user.id)
    return [model_to_read(model) for model in models]


@router.post("/{provider_id}/refresh", response_model=list[CustomModelProviderModelRead])
async def refresh_custom_provider_models(
    provider_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: DbSession,
    provider_policy_attributes: ProviderPolicyAttributesDependency,
) -> list[CustomModelProviderModelRead]:
    provider = await get_provider(session, provider_id=provider_id, user_id=current_user.id)
    if provider is None:
        raise _not_found()
    await _require_provider_policy(
        current_user, provider.id, ModelProviderPolicyPurpose.CONFIGURE, provider_policy_attributes
    )
    try:
        models = await refresh_provider_models(session, provider=provider, user_id=current_user.id)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return [model_to_read(model) for model in models]


@router.post(
    "/{provider_id}/models",
    response_model=CustomModelProviderModelRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_custom_provider_model(
    provider_id: UUID,
    payload: CustomModelProviderModelCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: DbSession,
    provider_policy_attributes: ProviderPolicyAttributesDependency,
) -> CustomModelProviderModelRead:
    provider = await get_provider(session, provider_id=provider_id, user_id=current_user.id)
    if provider is None:
        raise _not_found()
    await _require_provider_policy(
        current_user, provider.id, ModelProviderPolicyPurpose.CONFIGURE, provider_policy_attributes
    )
    model = await add_manual_model(
        session,
        provider=provider,
        user_id=current_user.id,
        model_id=payload.model_id,
    )
    return model_to_read(model)


@router.delete("/{provider_id}/models/{model_id:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_provider_model(
    provider_id: UUID,
    model_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: DbSession,
    provider_policy_attributes: ProviderPolicyAttributesDependency,
) -> Response:
    provider = await get_provider(session, provider_id=provider_id, user_id=current_user.id)
    if provider is None:
        raise _not_found()
    await _require_provider_policy(
        current_user, provider.id, ModelProviderPolicyPurpose.CONFIGURE, provider_policy_attributes
    )
    model = await remove_manual_model(
        session,
        provider=provider,
        user_id=current_user.id,
        model_id=model_id,
    )
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual model not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = [
    "CustomModelProviderCreate",
    "CustomModelProviderModelCreate",
    "CustomModelProviderUpdate",
    "router",
]
