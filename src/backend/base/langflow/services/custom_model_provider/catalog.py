from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from .service import list_models, list_providers

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

CUSTOM_PROVIDER_PREFIX = "custom-openai-compatible:"


def custom_provider_identity(provider_id: UUID) -> str:
    return f"{CUSTOM_PROVIDER_PREFIX}{provider_id}"


def parse_custom_provider_identity(value: str) -> UUID | None:
    if not value.startswith(CUSTOM_PROVIDER_PREFIX):
        return None
    try:
        provider_id = UUID(value.removeprefix(CUSTOM_PROVIDER_PREFIX))
    except ValueError:
        return None
    return provider_id if value == custom_provider_identity(provider_id) else None


async def custom_provider_catalog(
    db: AsyncSession, *, user_id: UUID | str, include_unavailable: bool = False
) -> list[dict]:
    catalog: list[dict] = []
    for provider in await list_providers(db, user_id=user_id):
        identity = custom_provider_identity(provider.id)
        models = await list_models(db, provider=provider, user_id=user_id, include_unavailable=include_unavailable)
        catalog.append(
            {
                "provider": identity,
                "provider_id": identity,
                "display_name": provider.name,
                "icon": "Plug",
                "models": [
                    {
                        "model_name": model.model_id,
                        "metadata": {
                            "model_type": "llm",
                            "tool_calling": True,
                            "default": True,
                            "custom_provider": True,
                            "provider_display_name": provider.name,
                            "available": model.available,
                        },
                    }
                    for model in models
                ],
                "num_models": len(models),
                "is_configured": True,
                "is_enabled": bool(models),
                "live_discovery": True,
                "custom_provider": True,
            }
        )
    return catalog
