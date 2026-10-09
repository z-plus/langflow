from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from langflow.api.v1 import models as models_module
from langflow.api.v1.models import DefaultModelRequest
from lfx.services.model_provider_policy import (
    ModelProviderPolicyContext,
    ModelProviderPolicyPurpose,
    ModelProviderPolicySnapshot,
)


async def _snapshot(current_user, providers, purpose, attributes=None):
    _ = attributes
    candidates = frozenset(providers)
    return ModelProviderPolicySnapshot(
        context=ModelProviderPolicyContext(user_id=current_user.id),
        purpose=purpose,
        candidate_provider_ids=candidates,
        allowed_provider_ids=candidates,
    )


@pytest.mark.asyncio
async def test_default_model_read_reports_custom_reference_diagnostics(monkeypatch):
    provider_id = uuid4()
    provider = f"custom-openai-compatible:{provider_id}"
    user = SimpleNamespace(id=uuid4())
    session = SimpleNamespace()
    provider_ref = SimpleNamespace(name="Gateway", deleted_at=None)
    stored = {
        "model_name": "qwen3",
        "provider": provider,
        "model_type": "language",
    }

    class FakeVariableService:
        value = json.dumps(stored)

        async def get_variable_object(self, **_kwargs):
            return self

    async def _available(_session, **kwargs):
        assert kwargs["provider_id"] == provider_id
        assert kwargs["user_id"] == user.id
        return provider_ref, SimpleNamespace(available=True)

    async def _deleted(_session, **_kwargs):
        return SimpleNamespace(name="Gateway", deleted_at=object()), SimpleNamespace(available=True)

    monkeypatch.setattr(models_module, "DatabaseVariableService", FakeVariableService)
    monkeypatch.setattr(models_module, "get_variable_service", lambda: FakeVariableService())
    monkeypatch.setattr(models_module, "_aresolve_policy_for_providers", _snapshot)
    monkeypatch.setattr(models_module, "resolve_provider_model_reference", _available)

    result = await models_module.get_default_model(
        session=session,
        current_user=user,
        provider_policy_attributes={},
        model_type="language",
    )
    assert result["default_model"] == {
        **stored,
        "provider_name": "Gateway",
        "available": True,
        "status": "available",
    }

    monkeypatch.setattr(models_module, "resolve_provider_model_reference", _deleted)
    result = await models_module.get_default_model(
        session=session,
        current_user=user,
        provider_policy_attributes={},
        model_type="language",
    )
    assert result["default_model"]["available"] is False
    assert result["default_model"]["status"] == "provider_deleted"


@pytest.mark.asyncio
async def test_default_model_write_rejects_unavailable_custom_reference(monkeypatch):
    provider_id = uuid4()
    provider = f"custom-openai-compatible:{provider_id}"
    user = SimpleNamespace(id=uuid4())
    session = SimpleNamespace()

    async def allowed(*_args, **_kwargs):
        return None

    async def unavailable(_session, **_kwargs):
        return SimpleNamespace(deleted_at=None), SimpleNamespace(available=False)

    async def denied_write(**_kwargs):
        pytest.fail("Unavailable custom model must not write the default variable")

    monkeypatch.setattr(models_module, "_require_provider", allowed)
    monkeypatch.setattr(models_module, "ensure_variable_permission", denied_write)
    monkeypatch.setattr(models_module, "resolve_provider_model_reference", unavailable)

    with pytest.raises(HTTPException, match="not available"):
        await models_module.set_default_model(
            session=session,
            current_user=user,
            provider_policy_attributes={},
            request=DefaultModelRequest(
                model_name="qwen3",
                provider=provider,
                model_type="language",
            ),
        )


@pytest.mark.asyncio
async def test_enabled_model_result_merges_custom_catalog(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    provider = f"custom-openai-compatible:{uuid4()}"
    custom_catalog = [
        {
            "provider": provider,
            "models": [
                {
                    "model_name": "qwen3",
                    "metadata": {"model_type": "llm", "custom_provider": True, "default": True},
                }
            ],
        }
    ]

    async def allowed(_current_user, providers, purpose, attributes=None):
        _ = attributes
        candidates = frozenset(providers)
        return ModelProviderPolicySnapshot(
            context=ModelProviderPolicyContext(user_id=_current_user.id),
            purpose=purpose,
            candidate_provider_ids=candidates,
            allowed_provider_ids=candidates,
        )

    monkeypatch.setattr(models_module, "get_unified_models_detailed", lambda **_kwargs: [])
    monkeypatch.setattr(models_module, "_get_disabled_models", _empty_set)
    monkeypatch.setattr(models_module, "_get_enabled_models", _empty_set)
    monkeypatch.setattr(models_module, "replace_with_live_models", lambda models, *_args: models)

    result = await models_module._get_enabled_models_result(
        session=SimpleNamespace(),
        current_user=user,
        provider_policy=await allowed(user, [provider], ModelProviderPolicyPurpose.CONFIGURE),
        custom_catalog=custom_catalog,
    )

    assert result["enabled_models"][provider]["qwen3"] is True
    assert result["enabled_models_by_type"][provider]["llm"]["qwen3"] is True


@pytest.mark.asyncio
async def test_enabled_models_policy_includes_custom_providers(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    provider = f"custom-openai-compatible:{uuid4()}"
    custom_catalog = [{"provider": provider, "models": []}]
    captured_providers = None

    async def capture_policy(_current_user, _purpose, *, providers, **_kwargs):
        nonlocal captured_providers
        captured_providers = providers
        return await _snapshot(
            _current_user,
            providers,
            ModelProviderPolicyPurpose.CONFIGURE,
        )

    async def enabled_result(**_kwargs):
        return {"enabled_models": {}}

    async def catalog(*_args, **_kwargs):
        return custom_catalog

    monkeypatch.setattr(models_module, "custom_provider_catalog", catalog)
    monkeypatch.setattr(models_module, "_aresolve_read_policy", capture_policy)
    monkeypatch.setattr(models_module, "_get_enabled_models_result", enabled_result)

    await models_module.get_enabled_models(
        session=SimpleNamespace(),
        current_user=user,
        provider_policy_attributes={},
    )

    assert provider in captured_providers


@pytest.mark.asyncio
async def test_enabled_model_result_keeps_unavailable_saved_option_disabled(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    provider = f"custom-openai-compatible:{uuid4()}"
    custom_catalog = [
        {
            "provider": provider,
            "models": [
                {
                    "model_name": "removed-upstream",
                    "metadata": {"model_type": "llm", "custom_provider": True, "available": False},
                }
            ],
        }
    ]

    monkeypatch.setattr(models_module, "get_unified_models_detailed", lambda **_kwargs: [])
    monkeypatch.setattr(models_module, "_get_disabled_models", _empty_set)
    monkeypatch.setattr(models_module, "_get_enabled_models", _empty_set)
    monkeypatch.setattr(models_module, "replace_with_live_models", lambda models, *_args: models)

    result = await models_module._get_enabled_models_result(
        session=SimpleNamespace(),
        current_user=user,
        provider_policy=await _snapshot(user, [provider], ModelProviderPolicyPurpose.CONFIGURE),
        custom_catalog=custom_catalog,
    )

    assert result["enabled_models"].get(provider, {}).get("removed-upstream") is not True


async def _empty_set(*_args, **_kwargs):
    return set()
