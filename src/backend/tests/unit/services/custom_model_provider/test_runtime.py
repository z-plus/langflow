from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langflow.services.custom_model_provider import chat_adapter, runtime
from lfx.base.models.unified_models import instantiation


@pytest.mark.asyncio
async def test_runtime_config_requires_owned_active_available_model(session, monkeypatch):
    user_id = uuid4()
    other_user_id = uuid4()
    provider_id = uuid4()
    provider = SimpleNamespace(
        id=provider_id,
        user_id=user_id,
        base_url="https://gateway.example/v1",
        api_key="encrypted",
        deleted_at=None,
    )
    model = SimpleNamespace(available=True)

    @asynccontextmanager
    async def scoped_session():
        yield session

    async def resolve(_session, *, provider_id, user_id, model_id):
        assert provider_id == provider.id
        assert model_id == "qwen3"
        return (provider, model) if user_id == provider.user_id else (None, None)

    monkeypatch.setattr(runtime, "session_scope", scoped_session)
    monkeypatch.setattr(runtime, "resolve_provider_model_reference", resolve)
    monkeypatch.setattr(runtime, "get_provider_api_key", lambda _provider: "top-secret")

    config = await runtime.resolve_custom_provider_runtime_config(
        provider_id=provider.id,
        user_id=user_id,
        model_id="qwen3",
    )
    assert config.base_url == provider.base_url
    assert config.api_key == "top-secret"
    assert "top-secret" not in repr(config)

    with pytest.raises(ValueError, match="provider is unavailable"):
        await runtime.resolve_custom_provider_runtime_config(
            provider_id=provider.id,
            user_id=other_user_id,
            model_id="qwen3",
        )

    provider.deleted_at = object()
    with pytest.raises(ValueError, match="provider is unavailable"):
        await runtime.resolve_custom_provider_runtime_config(
            provider_id=provider.id,
            user_id=user_id,
            model_id="qwen3",
        )

    provider.deleted_at = None
    model.available = False
    with pytest.raises(ValueError, match="model is unavailable"):
        await runtime.resolve_custom_provider_runtime_config(
            provider_id=provider.id,
            user_id=user_id,
            model_id="qwen3",
        )


@pytest.mark.parametrize("stream", [False, True])
def test_custom_runtime_builds_chat_openai_with_stored_secret_and_pinned_clients(monkeypatch, stream):
    provider_id = uuid4()
    user_id = uuid4()
    captured = {}

    async def resolve(**_kwargs):
        return runtime.CustomProviderRuntimeConfig(
            provider_id=provider_id,
            base_url="https://gateway.example/v1",
            api_key="top-secret",
        )

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(runtime, "resolve_custom_provider_runtime_config", resolve)
    monkeypatch.setattr(chat_adapter, "OpenAICompatibleReasoningChatModel", FakeChatOpenAI)
    monkeypatch.setattr(
        instantiation,
        "ssrf_protected_openai_clients_for_url",
        lambda url: {"http_client": f"sync:{url}", "http_async_client": f"async:{url}"},
    )

    result = instantiation._build_custom_provider_llm(
        provider=f"custom-openai-compatible:{provider_id}",
        model_name="qwen3",
        user_id=user_id,
        stream=stream,
        temperature=0.2,
        max_tokens=256,
    )

    assert isinstance(result, FakeChatOpenAI)
    assert captured["model"] == "qwen3"
    assert captured["streaming"] is stream
    assert captured["api_key"] == "top-secret"
    assert captured["base_url"] == "https://gateway.example/v1"
    assert captured["http_client"].startswith("sync:")
    assert captured["http_async_client"].startswith("async:")


def test_custom_provider_is_rejected_for_embeddings():
    provider = f"custom-openai-compatible:{uuid4()}"
    policy = SimpleNamespace(require=lambda _provider: None, require_model=lambda *_args, **_kwargs: None)

    with pytest.raises(ValueError, match="only support language models"):
        instantiation.get_embeddings(
            [{"provider": provider, "name": "qwen3", "metadata": {}}],
            user_id=uuid4(),
            provider_policy=policy,
        )


def test_success_callback_marks_provider_verified(monkeypatch):
    provider_id = uuid4()
    user_id = uuid4()
    marked = []

    async def mark(**kwargs):
        marked.append(kwargs)

    monkeypatch.setattr(runtime, "mark_custom_provider_verified", mark)
    callback = runtime.CustomProviderVerificationCallback(provider_id=provider_id, user_id=user_id)
    callback.on_llm_end(SimpleNamespace())

    assert marked == [{"provider_id": provider_id, "user_id": user_id}]


def test_custom_runtime_does_not_add_secret_to_provider_errors(monkeypatch):
    provider_id = uuid4()
    user_id = uuid4()

    async def resolve(**_kwargs):
        return runtime.CustomProviderRuntimeConfig(
            provider_id=provider_id,
            base_url="https://gateway.example/v1",
            api_key="top-secret",
        )

    class FailingChatOpenAI:
        def __init__(self, **_kwargs):
            pass

        def invoke(self, _input):
            message = "HTTP 401 from model provider"
            raise RuntimeError(message)

    monkeypatch.setattr(runtime, "resolve_custom_provider_runtime_config", resolve)
    monkeypatch.setattr(chat_adapter, "OpenAICompatibleReasoningChatModel", FailingChatOpenAI)
    monkeypatch.setattr(instantiation, "ssrf_protected_openai_clients_for_url", lambda _url: {})

    model = instantiation._build_custom_provider_llm(
        provider=f"custom-openai-compatible:{provider_id}",
        model_name="qwen3",
        user_id=user_id,
        stream=False,
        temperature=None,
        max_tokens=None,
    )
    with pytest.raises(RuntimeError, match="HTTP 401") as exc_info:
        model.invoke("hello")
    assert "top-secret" not in str(exc_info.value)
