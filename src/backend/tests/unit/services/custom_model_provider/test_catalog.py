from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from langflow.services.custom_model_provider import catalog


def test_custom_provider_identity_is_stable_and_canonical():
    provider_id = uuid4()
    identity = catalog.custom_provider_identity(provider_id)
    assert identity == f"custom-openai-compatible:{provider_id}"
    assert catalog.parse_custom_provider_identity(identity) == provider_id
    assert catalog.parse_custom_provider_identity(f"custom-openai-compatible:{str(provider_id).upper()}") is None
    assert catalog.parse_custom_provider_identity("openai") is None


@pytest.mark.asyncio
async def test_catalog_keeps_instances_and_duplicate_model_ids_distinct(monkeypatch):
    first_id, second_id = uuid4(), uuid4()
    owned_providers = [
        SimpleNamespace(id=first_id, name="Renamed Gateway"),
        SimpleNamespace(id=second_id, name="Backup"),
    ]
    other_provider = SimpleNamespace(id=uuid4(), name="Other User")
    calls = []

    async def list_owned(_db, *, user_id):
        calls.append(user_id)
        return owned_providers if user_id == UUID(int=1) else [other_provider]

    async def list_owned_models(_db, *, provider, user_id, include_unavailable):
        expected = owned_providers if user_id == UUID(int=1) else [other_provider]
        assert provider in expected
        assert include_unavailable is False
        return [SimpleNamespace(model_id="qwen3", available=True)]

    monkeypatch.setattr(catalog, "list_providers", list_owned)
    monkeypatch.setattr(catalog, "list_models", list_owned_models)
    result = await catalog.custom_provider_catalog(object(), user_id=UUID(int=1))

    assert calls == [UUID(int=1)]
    assert [entry["provider"] for entry in result] == [
        catalog.custom_provider_identity(first_id),
        catalog.custom_provider_identity(second_id),
    ]
    assert [entry["display_name"] for entry in result] == ["Renamed Gateway", "Backup"]
    assert [entry["models"][0]["model_name"] for entry in result] == ["qwen3", "qwen3"]
    assert all(entry["models"][0]["metadata"]["model_type"] == "llm" for entry in result)

    other_result = await catalog.custom_provider_catalog(object(), user_id=UUID(int=2))
    assert [entry["provider"] for entry in other_result] == [catalog.custom_provider_identity(other_provider.id)]
    assert not {entry["provider"] for entry in result} & {entry["provider"] for entry in other_result}


@pytest.mark.asyncio
async def test_catalog_can_recover_unavailable_models_with_availability_metadata(monkeypatch):
    provider = SimpleNamespace(id=uuid4(), name="Gateway")

    async def list_owned(_db, *, user_id):
        assert user_id == UUID(int=1)
        return [provider]

    async def list_owned_models(_db, *, provider, user_id, include_unavailable):
        assert provider.id is not None
        assert user_id == UUID(int=1)
        assert include_unavailable is True
        return [SimpleNamespace(model_id="qwen3", available=False)]

    monkeypatch.setattr(catalog, "list_providers", list_owned)
    monkeypatch.setattr(catalog, "list_models", list_owned_models)
    result = await catalog.custom_provider_catalog(object(), user_id=UUID(int=1), include_unavailable=True)

    model = result[0]["models"][0]
    assert model["metadata"]["available"] is False
