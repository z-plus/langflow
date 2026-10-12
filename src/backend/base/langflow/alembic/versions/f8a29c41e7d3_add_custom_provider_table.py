"""Add custom provider table

Revision ID: f8a29c41e7d3
Revises: 386662af02e9
Create Date: 2026-10-10 13:00:00.000000

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from langflow.utils import migration
from sqlmodel.sql.sqltypes import AutoString

# revision identifiers, used by Alembic.
revision: str = "f8a29c41e7d3"  # pragma: allowlist secret
down_revision: str | None = "386662af02e9"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "custom_provider"
UNIQUE_CONSTRAINT_NAME = "uq_custom_provider_user_provider"


def upgrade() -> None:
    conn = op.get_bind()
    if migration.table_exists(TABLE_NAME, conn):
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", AutoString(), nullable=False),
        sa.Column("display_name", AutoString(), nullable=False),
        sa.Column("base_url", AutoString(), nullable=False),
        sa.Column("api_key", AutoString(), nullable=False),  # MUST be stored encrypted
        sa.Column("validation_status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("validation_error", AutoString(), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discovered_models", sa.JSON(), nullable=True),
        sa.Column("manual_models", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_custom_provider_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_custom_provider")),
        sa.UniqueConstraint("user_id", "provider_id", name=UNIQUE_CONSTRAINT_NAME),
    )

    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_custom_provider_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    if not migration.table_exists(TABLE_NAME, conn):
        return

    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_custom_provider_user_id"))

    op.drop_table(TABLE_NAME)
