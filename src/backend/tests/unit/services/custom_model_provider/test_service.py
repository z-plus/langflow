from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from langflow.services.custom_model_provider.service import (
    CustomProviderCredentialError,
    add_manual_model,
    create_provider,
    get_provider,
    get_provider_api_key,
    list_models,
    list_providers,
    refresh_provider_models,
    remove_manual_model,
    resolve_provider_model_reference,
    soft_delete_provider,
    to_read,
    update_provider,
    verify_provider,
)
from langflow.services.database.models.custom_model_provider import CustomModelProvider, CustomModelProviderModel
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: sa.Table(
                "user",
                sa.MetaData(),
                sa.Column("id", sa.Uuid(), primary_key=True),
            ).create(sync)
        )
        await connection.run_sync(CustomModelProvider.__table__.create)
        await connection.run_sync(CustomModelProviderModel.__table__.create)
    async with AsyncSession(engine, expire_on_commit=False) as db:
        yield db
    await engine.dispose()


@pytest.fixture(autouse=True)
def credential_cipher(monkeypatch):
    monkeypatch.setattr(
        "langflow.services.custom_model_provider.service.auth_utils.encrypt_api_key",
        lambda value: f"encrypted:{value}",
    )
    monkeypatch.setattr(
        "langflow.services.custom_model_provider.service.auth_utils.decrypt_api_key",
        lambda value: value.removeprefix("encrypted:"),
    )


@pytest.mark.asyncio
async def test_provider_reads_are_owner_scoped_and_mask_credentials(session):
    owner_id, other_id = uuid4(), uuid4()
    provider = await create_provider(
        session,
        user_id=owner_id,
        name="Local",
        base_url="https://example.test/v1",
        api_key="secret",
    )

    assert await get_provider(session, provider_id=provider.id, user_id=other_id) is None
    assert await list_providers(session, user_id=other_id) == []
    public = to_read(provider)
    assert public.has_api_key is True
    assert "api_key" not in public.model_dump()
    assert "secret" not in public.model_dump_json()


@pytest.mark.asyncio
async def test_update_omits_or_replaces_key_and_detects_decryption_failure(session, monkeypatch):
    user_id = uuid4()
    provider = await create_provider(
        session,
        user_id=user_id,
        name="Local",
        base_url="https://example.test/v1",
        api_key="first",
    )
    original_ciphertext = provider.api_key
    await update_provider(session, provider=provider, user_id=user_id, name="Renamed")
    assert provider.api_key == original_ciphertext

    await update_provider(session, provider=provider, user_id=user_id, api_key="second")
    assert provider.api_key == "encrypted:second"
    assert get_provider_api_key(provider) == "second"

    monkeypatch.setattr(
        "langflow.services.custom_model_provider.service.auth_utils.decrypt_api_key",
        lambda _value: "",
    )
    with pytest.raises(CustomProviderCredentialError, match="decrypt"):
        get_provider_api_key(provider)


@pytest.mark.asyncio
async def test_soft_delete_erases_ciphertext_and_hides_provider(session):
    user_id = uuid4()
    provider = await create_provider(
        session,
        user_id=user_id,
        name="Disposable",
        base_url="https://example.test/v1",
        api_key="secret",
    )
    await soft_delete_provider(session, provider=provider, user_id=user_id)

    assert provider.api_key is None
    assert provider.deleted_at is not None
    assert await get_provider(session, provider_id=provider.id, user_id=user_id) is None
    deleted = await get_provider(session, provider_id=provider.id, user_id=user_id, include_deleted=True)
    assert deleted is provider


@pytest.mark.asyncio
async def test_saved_reference_survives_rename_and_reports_unavailable_or_deleted(session):
    user_id = uuid4()
    provider = await create_provider(
        session,
        user_id=user_id,
        name="Original",
        base_url="https://example.test/v1",
        api_key="secret",
    )
    await add_manual_model(session, provider=provider, user_id=user_id, model_id="qwen3")

    await update_provider(session, provider=provider, user_id=user_id, name="Renamed")
    resolved_provider, resolved_model = await resolve_provider_model_reference(
        session, provider_id=provider.id, user_id=user_id, model_id="qwen3"
    )
    assert resolved_provider is provider
    assert resolved_provider.name == "Renamed"
    assert resolved_model is not None
    assert resolved_model.available is True

    model_ref = resolved_model
    model_ref.available = False
    session.add(model_ref)
    await session.flush()
    _, model_ref = await resolve_provider_model_reference(
        session, provider_id=provider.id, user_id=user_id, model_id="qwen3"
    )
    assert model_ref is not None
    assert model_ref.available is False

    await soft_delete_provider(session, provider=provider, user_id=user_id)
    old_provider, old_model = await resolve_provider_model_reference(
        session, provider_id=provider.id, user_id=user_id, model_id="qwen3"
    )
    assert old_provider is provider
    assert old_provider.deleted_at is not None
    assert old_model is not None
    assert old_model.model_id == "qwen3"

    replacement = await create_provider(
        session,
        user_id=user_id,
        name="Renamed",
        base_url="https://example.test/v1",
        api_key="secret",
    )
    assert replacement.id != provider.id
    again_provider, again_model = await resolve_provider_model_reference(
        session, provider_id=provider.id, user_id=user_id, model_id="qwen3"
    )
    assert again_provider is provider
    assert again_model is old_model

    assert await resolve_provider_model_reference(
        session, provider_id=provider.id, user_id=uuid4(), model_id="qwen3"
    ) == (None, None)


@pytest.mark.asyncio
async def test_verification_persists_success_and_failure(session, monkeypatch):
    user_id = uuid4()
    provider = await create_provider(
        session,
        user_id=user_id,
        name="Verified",
        base_url="https://example.test/v1",
        api_key="secret",
    )
    monkeypatch.setattr(
        "langflow.services.custom_model_provider.client.discover_model_ids",
        lambda _url, _key: ["qwen"],
    )
    assert await verify_provider(session, provider=provider) == ["qwen"]
    assert provider.is_verified is True
    assert provider.verification_error is None

    from langflow.services.custom_model_provider.client import ModelDiscoveryError

    def fail(_url, _key):
        msg = "Authentication failed"
        raise ModelDiscoveryError(msg)

    monkeypatch.setattr("langflow.services.custom_model_provider.client.discover_model_ids", fail)
    assert await verify_provider(session, provider=provider) == []
    assert provider.is_verified is False
    assert provider.verification_error == "Authentication failed"


@pytest.mark.asyncio
async def test_refresh_merges_sources_preserves_manual_and_marks_missing_unavailable(session, monkeypatch):
    user_id = uuid4()
    provider = await create_provider(
        session,
        user_id=user_id,
        name="Models",
        base_url="https://example.test/v1",
        api_key="secret",
    )
    manual = await add_manual_model(session, provider=provider, user_id=user_id, model_id="manual")
    duplicate = await add_manual_model(session, provider=provider, user_id=user_id, model_id="both")
    monkeypatch.setattr(
        "langflow.services.custom_model_provider.client.discover_model_ids",
        lambda _url, _key: ["both", "remote"],
    )
    refreshed = await refresh_provider_models(session, provider=provider, user_id=user_id)
    by_id = {model.model_id: model for model in refreshed}
    assert by_id["manual"].manually_added is True
    assert by_id["manual"].available is True
    assert by_id["both"].id == duplicate.id
    assert by_id["both"].manually_added is True
    assert by_id["both"].discovered is True
    assert by_id["remote"].discovered is True

    monkeypatch.setattr(
        "langflow.services.custom_model_provider.client.discover_model_ids",
        lambda _url, _key: [],
    )
    refreshed = await refresh_provider_models(session, provider=provider, user_id=user_id)
    by_id = {model.model_id: model for model in refreshed}
    assert by_id["manual"].available is True
    assert by_id["both"].available is True
    assert by_id["remote"].available is False
    assert manual.id == by_id["manual"].id


@pytest.mark.asyncio
async def test_remove_manual_source_preserves_discovered_membership(session, monkeypatch):
    user_id = uuid4()
    provider = await create_provider(
        session,
        user_id=user_id,
        name="Sources",
        base_url="https://example.test/v1",
        api_key="secret",
    )
    await add_manual_model(session, provider=provider, user_id=user_id, model_id="both")
    monkeypatch.setattr(
        "langflow.services.custom_model_provider.client.discover_model_ids",
        lambda _url, _key: ["both"],
    )
    await refresh_provider_models(session, provider=provider, user_id=user_id)
    removed = await remove_manual_model(session, provider=provider, user_id=user_id, model_id="both")
    assert removed is not None
    assert removed.manually_added is False
    assert removed.discovered is True
    assert removed.available is True
    assert len(await list_models(session, provider=provider, user_id=user_id)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["edit", "delete"])
async def test_refresh_rejects_concurrent_provider_change(monkeypatch, change):
    user_id = uuid4()
    now = datetime.now(timezone.utc)
    provider = CustomModelProvider(
        user_id=user_id,
        name="Concurrent",
        normalized_name="concurrent",
        base_url="https://example.test/v1",
        api_key="encrypted:key",
        created_at=now,
        updated_at=now,
    )

    async def discover_then_change(_func, *_args):
        if change == "delete":
            provider.deleted_at = now
        else:
            provider.updated_at = now + timedelta(seconds=1)
        return ["qwen"]

    async def refresh(_provider):
        return None

    monkeypatch.setattr(
        "langflow.services.custom_model_provider.service.asyncio.to_thread",
        discover_then_change,
    )
    fake_db = SimpleNamespace(refresh=refresh)
    with pytest.raises(RuntimeError, match="changed"):
        await refresh_provider_models(fake_db, provider=provider, user_id=user_id)
