"""Add per-user custom OpenAI-compatible model providers.

Revision ID: f4c8d2e6a1b3
Revises: a1b2c9d3e4f5
Create Date: 2026-10-08

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4c8d2e6a1b3"  # pragma: allowlist secret
down_revision: str | None = "a1b2c9d3e4f5"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROVIDER_TABLE = "custom_model_provider"
MODEL_TABLE = "custom_model_provider_model"
ACTIVE_NAME_INDEX = "uq_custom_model_provider_active_name"


def upgrade() -> None:
    op.create_table(
        PROVIDER_TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column("api_key", sa.String(), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verification_error", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_custom_model_provider_user_id", PROVIDER_TABLE, ["user_id"])
    op.create_index(
        ACTIVE_NAME_INDEX,
        PROVIDER_TABLE,
        ["user_id", "normalized_name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        MODEL_TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.String(length=200), nullable=False),
        sa.Column("manually_added", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("discovered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["provider_id"], [f"{PROVIDER_TABLE}.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "model_id", name="uq_custom_model_provider_model_id"),
    )
    op.create_index("ix_custom_model_provider_model_provider_id", MODEL_TABLE, ["provider_id"])


def downgrade() -> None:
    op.drop_index("ix_custom_model_provider_model_provider_id", table_name=MODEL_TABLE)
    op.drop_table(MODEL_TABLE)
    op.drop_index(ACTIVE_NAME_INDEX, table_name=PROVIDER_TABLE)
    op.drop_index("ix_custom_model_provider_user_id", table_name=PROVIDER_TABLE)
    op.drop_table(PROVIDER_TABLE)
