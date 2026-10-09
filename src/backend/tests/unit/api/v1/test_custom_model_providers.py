from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from langflow.api.v1 import custom_model_providers as api
from langflow.services.auth.utils import get_current_active_user
from langflow.services.custom_model_provider import custom_provider_identity
from lfx.base.models.provider_registry import resolve_provider_id
from lfx.services.deps import injectable_session_scope, injectable_session_scope_readonly
from lfx.services.model_provider_policy import (
    ModelProviderPolicyContext,
    ModelProviderPolicyPurpose,
    ModelProviderPolicySnapshot,
)


def _provider(*, user_id=None, name="Gateway", api_key="encrypted:key"):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id or uuid4(),
        name=name,
        base_url="https://example.test/v1",
        api_key=api_key,
        is_verified=False,
        verification_error="Discovery has not run",
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


async def _session():
    yield SimpleNamespace()


def _client(user_id=None):
    app = FastAPI()
    app.include_router(api.router)
    user = SimpleNamespace(id=user_id or uuid4())
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[injectable_session_scope] = _session
    app.dependency_overrides[injectable_session_scope_readonly] = _session
    return TestClient(app), user


def _denied_policy(*, user_id, providers, purpose, attributes=None):
    _ = attributes
    candidates = frozenset(resolve_provider_id(provider) for provider in providers)
    return ModelProviderPolicySnapshot(
        context=ModelProviderPolicyContext(user_id=user_id),
        purpose=purpose,
        candidate_provider_ids=candidates,
        allowed_provider_ids=frozenset(),
    )


def test_custom_provider_routes_require_authentication():
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[injectable_session_scope] = _session
    app.dependency_overrides[injectable_session_scope_readonly] = _session

    def reject():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    app.dependency_overrides[get_current_active_user] = reject
    assert TestClient(app).get("/models/custom-providers").status_code == status.HTTP_401_UNAUTHORIZED


def test_create_lists_and_masks_provider(monkeypatch):
    client, user = _client()
    provider = _provider(user_id=user.id)
    captured = {}

    async def create(_session, **kwargs):
        captured.update(kwargs)
        return provider

    async def list_all(_session, **kwargs):
        assert kwargs == {"user_id": user.id}
        return [provider]

    async def refresh(_session, **kwargs):
        assert kwargs == {"provider": provider, "user_id": user.id}
        return []

    monkeypatch.setattr(api, "create_provider", create)
    monkeypatch.setattr(api, "list_providers", list_all)
    monkeypatch.setattr(api, "refresh_provider_models", refresh)
    response = client.post(
        "/models/custom-providers",
        json={"name": " Gateway ", "base_url": "HTTPS://EXAMPLE.TEST:443/v1/", "api_key": " secret "},
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["has_api_key"] is True
    assert "api_key" not in response.json()
    assert captured == {
        "user_id": user.id,
        "name": "Gateway",
        "base_url": "https://example.test/v1",
        "api_key": "secret",
    }
    assert client.get("/models/custom-providers").json()[0]["name"] == "Gateway"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"name": "", "base_url": "https://example.test", "api_key": "key"}, "name"),
        ({"name": "x", "base_url": "ftp://example.test", "api_key": "key"}, "base_url"),
        ({"name": "x", "base_url": "https://example.test", "api_key": ""}, "api_key"),
    ],
)
def test_create_rejects_invalid_fields(payload, field):
    response = _client()[0].post("/models/custom-providers", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["detail"][0]["loc"][-1] == field


def test_duplicate_name_is_a_conflict(monkeypatch):
    async def duplicate(*_args, **_kwargs):
        msg = "An active custom provider with this name already exists"
        raise ValueError(msg)

    monkeypatch.setattr(api, "create_provider", duplicate)
    response = _client()[0].post(
        "/models/custom-providers",
        json={"name": "gateway", "base_url": "https://example.test", "api_key": "key"},
    )
    assert response.status_code == status.HTTP_409_CONFLICT


def test_read_uses_owner_scope_and_hides_foreign_provider(monkeypatch):
    requested = uuid4()
    client, user = _client()

    async def missing(_session, **kwargs):
        assert kwargs == {"provider_id": requested, "user_id": user.id}

    monkeypatch.setattr(api, "get_provider", missing)
    assert client.get(f"/models/custom-providers/{requested}").status_code == status.HTTP_404_NOT_FOUND


def test_rename_without_api_key_replacement_and_delete(monkeypatch):
    client, user = _client()
    provider = _provider(user_id=user.id)
    update_payload = None
    deleted = False

    async def get_owned(_session, **_kwargs):
        return provider

    async def update(_session, **kwargs):
        nonlocal update_payload
        update_payload = kwargs
        provider.name = kwargs["name"]
        return provider

    async def delete(_session, **kwargs):
        nonlocal deleted
        assert kwargs == {"provider": provider, "user_id": user.id}
        deleted = True

    async def refresh(_session, **_kwargs):
        pytest.fail("A rename-only update must not trigger discovery")

    monkeypatch.setattr(api, "get_provider", get_owned)
    monkeypatch.setattr(api, "update_provider", update)
    monkeypatch.setattr(api, "soft_delete_provider", delete)
    monkeypatch.setattr(api, "refresh_provider_models", refresh)

    response = client.patch(f"/models/custom-providers/{provider.id}", json={"name": "Renamed"})
    assert response.status_code == status.HTTP_200_OK
    assert update_payload == {"provider": provider, "user_id": user.id, "name": "Renamed"}
    assert client.delete(f"/models/custom-providers/{provider.id}").status_code == status.HTTP_204_NO_CONTENT
    assert deleted is True


def test_delete_manual_model_accepts_namespaced_id(monkeypatch):
    client, user = _client()
    provider = _provider(user_id=user.id)
    captured_model_id = None

    async def get_owned(*_args, **_kwargs):
        return provider

    async def remove(_session, **kwargs):
        nonlocal captured_model_id
        captured_model_id = kwargs["model_id"]
        return SimpleNamespace()

    monkeypatch.setattr(api, "get_provider", get_owned)
    monkeypatch.setattr(api, "remove_manual_model", remove)

    response = client.delete(f"/models/custom-providers/{provider.id}/models/org/model-name")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert captured_model_id == "org/model-name"


def test_discover_policy_hides_custom_provider(monkeypatch):
    client, user = _client()
    provider = _provider(user_id=user.id)

    async def list_all(*_args, **_kwargs):
        return [provider]

    async def deny(**kwargs):
        assert kwargs["purpose"] is ModelProviderPolicyPurpose.DISCOVER
        assert kwargs["providers"] == [custom_provider_identity(provider.id)]
        return _denied_policy(**kwargs)

    monkeypatch.setattr(api, "list_providers", list_all)
    monkeypatch.setattr(api, "aresolve_model_provider_policy", deny)

    response = client.get("/models/custom-providers")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


def test_configure_policy_denial_returns_non_enumerating_not_found(monkeypatch):
    client, user = _client()
    provider = _provider(user_id=user.id)

    async def get_owned(*_args, **_kwargs):
        return provider

    async def deny(**kwargs):
        assert kwargs["purpose"] is ModelProviderPolicyPurpose.CONFIGURE
        return _denied_policy(**kwargs)

    async def update(*_args, **_kwargs):
        pytest.fail("Denied configuration must not mutate the provider")

    monkeypatch.setattr(api, "get_provider", get_owned)
    monkeypatch.setattr(api, "aresolve_model_provider_policy", deny)
    monkeypatch.setattr(api, "update_provider", update)

    response = client.patch(f"/models/custom-providers/{provider.id}", json={"name": "Hidden"})
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "Custom provider not found"}
