"""Schema coverage for custom OpenAI-compatible model providers."""

from __future__ import annotations

import importlib
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

_MIGRATION = importlib.import_module("langflow.alembic.versions.f4c8d2e6a1b3_add_custom_model_providers")


def test_custom_model_provider_migration_upgrades_and_downgrades_sqlite(monkeypatch):
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    sa.Table("user", metadata, sa.Column("id", sa.Uuid(), primary_key=True))
    metadata.create_all(engine)

    with engine.begin() as connection:
        monkeypatch.setattr(_MIGRATION, "op", Operations(MigrationContext.configure(connection)))
        _MIGRATION.upgrade()

        inspector = sa.inspect(connection)
        assert {_MIGRATION.PROVIDER_TABLE, _MIGRATION.MODEL_TABLE} <= set(inspector.get_table_names())
        provider_indexes = {index["name"]: index for index in inspector.get_indexes(_MIGRATION.PROVIDER_TABLE)}
        assert provider_indexes[_MIGRATION.ACTIVE_NAME_INDEX]["unique"] == 1
        assert provider_indexes[_MIGRATION.ACTIVE_NAME_INDEX]["column_names"] == ["user_id", "normalized_name"]

        provider = sa.Table(_MIGRATION.PROVIDER_TABLE, sa.MetaData(), autoload_with=connection)
        user_id = uuid4()
        connection.execute(sa.text('INSERT INTO "user" (id) VALUES (:id)'), {"id": user_id.hex})
        values = {
            "id": uuid4().hex,
            "user_id": user_id.hex,
            "name": "First",
            "normalized_name": "first",
            "base_url": "https://example.test/v1",
        }
        connection.execute(provider.insert(), values)
        with pytest.raises(IntegrityError):
            connection.execute(provider.insert(), {**values, "id": uuid4().hex, "name": "FIRST"})

        connection.execute(provider.update().values(deleted_at=sa.func.now()))
        connection.execute(provider.insert(), {**values, "id": uuid4().hex, "name": "FIRST"})

        _MIGRATION.downgrade()
        assert _MIGRATION.MODEL_TABLE not in sa.inspect(connection).get_table_names()
        assert _MIGRATION.PROVIDER_TABLE not in sa.inspect(connection).get_table_names()


def test_active_name_index_compiles_for_postgresql():
    table = sa.Table(
        _MIGRATION.PROVIDER_TABLE,
        sa.MetaData(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("normalized_name", sa.String(200), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    index = sa.Index(
        _MIGRATION.ACTIVE_NAME_INDEX,
        table.c.user_id,
        table.c.normalized_name,
        unique=True,
        postgresql_where=table.c.deleted_at.is_(None),
    )

    sql = str(sa.schema.CreateIndex(index).compile(dialect=postgresql.dialect()))
    assert sql == (
        "CREATE UNIQUE INDEX uq_custom_model_provider_active_name "
        "ON custom_model_provider (user_id, normalized_name) WHERE deleted_at IS NULL"
    )
