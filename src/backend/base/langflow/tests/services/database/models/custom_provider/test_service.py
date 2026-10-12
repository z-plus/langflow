from __future__ import annotations

from unittest.mock import patch

import pytest
from langflow.services.database.models.custom_provider.service import (
    add_manual_model,
    build_catalog_entries,
    create_custom_provider,
    refresh_custom_provider,
    remove_manual_model,
    update_custom_provider,
)
from langflow.services.database.models.user.model import User
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

_ENCRYPT = "langflow.services.database.models.custom_provider.crud.auth_utils.encrypt_api_key"
_DECRYPT = "langflow.services.database.models.custom_provider.crud.auth_utils.decrypt_api_key"
_BUILTIN_IDS = "langflow.services.database.models.custom_provider.service._builtin_provider_ids"
_TEST_PASSWORD = "hashed"  # noqa: S105  # pragma: allowlist secret


@pytest.fixture(name="db_engine")
def db_engine_fixture():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_connection, connection_record):  # noqa: ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@pytest.fixture(name="db")
async def db_fixture(db_engine):
    async with db_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        yield session
    async with db_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await db_engine.dispose()


@pytest.fixture
async def user(db: AsyncSession) -> User:
    u = User(username="testuser", password=_TEST_PASSWORD, is_active=True)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.fixture(autouse=True)
def _encryption():
    with (
        patch(_ENCRYPT, side_effect=lambda raw, *_a, **_kw: f"ENC::{raw}"),
        patch(_DECRYPT, side_effect=lambda enc, *_a, **_kw: enc.removeprefix("ENC::")),
    ):
        yield


async def _create(
    db, user, *, provider_id="mygateway", display_name="My Gateway", base_url="https://gw.example.com/v1"
):
    return await create_custom_provider(
        db,
        user_id=user.id,
        provider_id=provider_id,
        display_name=display_name,
        base_url=base_url,
        api_key="sk-secret-123",
    )


@pytest.mark.asyncio
async def test_create_stores_encrypted_key(db, user):
    provider = await _create(db, user)
    assert provider.api_key == "ENC::sk-secret-123"
    assert provider.validation_status == "draft"


@pytest.mark.asyncio
async def test_provider_id_validation(db, user):
    with pytest.raises(ValueError, match="Provider ID must start with a lowercase letter"):
        await _create(db, user, provider_id="UpperCase")
    with pytest.raises(ValueError, match="must be at most 100 characters"):
        await _create(db, user, provider_id="a" * 101)
    with pytest.raises(ValueError, match="Provider ID is required"):
        await _create(db, user, provider_id="   ")


@pytest.mark.asyncio
async def test_base_url_must_end_in_v1(db, user):
    with pytest.raises(ValueError, match="must end with /v1"):
        await _create(db, user, base_url="https://gw.example.com")
    with pytest.raises(ValueError, match="valid HTTP"):
        await _create(db, user, base_url="ftp://gw.example.com/v1")


@pytest.mark.asyncio
@patch(_BUILTIN_IDS, return_value={"openai", "openai-compatible"})
async def test_provider_id_collision_with_builtin_rejected(db, user):
    with pytest.raises(ValueError, match="collides with a built-in provider"):
        await _create(db, user, provider_id="openai")


@pytest.mark.asyncio
async def test_duplicate_provider_id_rejected(db, user):
    await _create(db, user, provider_id="mygateway")
    with pytest.raises(ValueError, match="Provider ID already exists"):
        await _create(db, user, provider_id="mygateway")


@pytest.mark.asyncio
async def test_duplicate_display_name_case_insensitive_rejected(db, user):
    await _create(db, user, display_name="My Gateway")
    with pytest.raises(ValueError, match="display name already exists"):
        await _create(db, user, display_name="my gateway", provider_id="other")


@pytest.mark.asyncio
async def test_update_display_name_and_credentials_changed(db, user):
    provider = await _create(db, user)
    updated, credentials_changed = await update_custom_provider(
        db, provider=provider, display_name="Renamed", base_url=provider.base_url
    )
    assert credentials_changed is False
    assert updated.display_name == "Renamed"

    updated2, credentials_changed2 = await update_custom_provider(db, provider=updated, api_key="sk-new")
    assert credentials_changed2 is True
    assert updated2.api_key == "ENC::sk-new"


@pytest.mark.asyncio
async def test_manual_model_add_and_remove_with_duplicate_check(db, user):
    provider = await _create(db, user)
    provider = await add_manual_model(db, provider=provider, model_id="qwen-2507", name="Qwen 2.5")
    with pytest.raises(ValueError, match="already exists"):
        await add_manual_model(db, provider=provider, model_id="qwen-2507")
    provider = await remove_manual_model(db, provider=provider, model_id="qwen-2507")
    assert provider.manual_models == []


@pytest.mark.asyncio
async def test_catalog_entries_shape(db, user):
    provider = await _create(db, user)
    provider.discovered_models = [
        {"model_id": "gpt-x", "model_type": "llm"},
        {"model_id": "embed-x", "model_type": "embeddings"},
    ]
    await db.commit()
    entries = await build_catalog_entries(db, user_id=user.id)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["provider"] == "mygateway"
    assert entry["custom"] is True
    assert entry["is_configured"] is True
    models = {m["model_name"]: m["metadata"] for m in entry["models"]}
    assert models["gpt-x"]["model_class"] == "ChatOpenAI"
    assert models["embed-x"]["embedding_class"] == "OpenAIEmbeddings"


@pytest.mark.asyncio
async def test_refresh_merge_semantics(db, user):
    provider = await _create(db, user)
    provider.discovered_models = [{"model_id": "old-model", "model_type": "llm"}]
    await db.commit()

    with patch(
        "langflow.services.database.models.custom_provider.service._discover_type",
        side_effect=lambda _url, _key, model_type: [{"model_id": "new-model", "model_type": model_type}],
    ):
        refreshed, error = await refresh_custom_provider(db, provider=provider)

    assert error is None
    assert refreshed.validation_status == "valid"
    ids = {(m["model_id"], m["model_type"]) for m in refreshed.discovered_models}
    assert ("old-model", "llm") in ids  # retained (merge)
    assert ("new-model", "llm") in ids
    assert ("new-model", "embeddings") in ids


@pytest.mark.asyncio
async def test_refresh_failure_marks_invalid(db, user):
    provider = await _create(db, user)
    with patch(
        "langflow.services.database.models.custom_provider.service._discover_type",
        side_effect=ValueError("Could not connect to https://gw.example.com"),
    ):
        refreshed, error = await refresh_custom_provider(db, provider=provider)
    assert error is not None
    assert refreshed.validation_status == "invalid"
    assert refreshed.validation_error == error


@pytest.mark.asyncio
async def test_decrypt_round_trip(db, user):
    from langflow.services.database.models.custom_provider.crud import _decrypt_api_key

    provider = await _create(db, user)
    assert _decrypt_api_key(provider.api_key) == "sk-secret-123"
