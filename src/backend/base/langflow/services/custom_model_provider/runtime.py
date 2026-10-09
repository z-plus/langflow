from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from langchain_core.callbacks import BaseCallbackHandler
from lfx.services.deps import session_scope

from .service import get_provider_api_key, resolve_provider_model_reference

if TYPE_CHECKING:
    from uuid import UUID


@dataclass(frozen=True, slots=True)
class CustomProviderRuntimeConfig:
    provider_id: UUID
    base_url: str
    api_key: str = field(repr=False)


async def resolve_custom_provider_runtime_config(
    *, provider_id: UUID, user_id: UUID | str | None, model_id: str
) -> CustomProviderRuntimeConfig:
    if user_id is None:
        msg = "A user is required to use a custom model provider"
        raise ValueError(msg)

    async with session_scope() as session:
        provider, model = await resolve_provider_model_reference(
            session,
            provider_id=provider_id,
            user_id=user_id,
            model_id=model_id,
        )
        if provider is None or provider.deleted_at is not None:
            msg = "Custom model provider is unavailable"
            raise ValueError(msg)
        if model is None or not model.available:
            msg = f"Custom model is unavailable: {model_id}"
            raise ValueError(msg)
        return CustomProviderRuntimeConfig(
            provider_id=provider.id,
            base_url=provider.base_url,
            api_key=get_provider_api_key(provider),
        )


async def mark_custom_provider_verified(*, provider_id: UUID, user_id: UUID | str) -> None:
    async with session_scope() as session:
        provider, _ = await resolve_provider_model_reference(
            session,
            provider_id=provider_id,
            user_id=user_id,
            model_id="__verification_only__",
        )
        if provider is None or provider.deleted_at is not None:
            return
        provider.is_verified = True
        provider.verification_error = None
        provider.updated_at = datetime.now(timezone.utc)
        session.add(provider)
        await session.flush()


class CustomProviderVerificationCallback(BaseCallbackHandler):
    """Mark a provider verified only after LangChain reports a successful model run."""

    def __init__(self, *, provider_id: UUID, user_id: UUID | str) -> None:
        self.provider_id = provider_id
        self.user_id = user_id

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:  # noqa: ARG002
        from lfx.utils.async_helpers import run_until_complete

        run_until_complete(mark_custom_provider_verified(provider_id=self.provider_id, user_id=self.user_id))
