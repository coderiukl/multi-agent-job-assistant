"""create conversation turns

Revision ID: e52b1cb8a9f4
Revises: d41f0a8c7e21
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e52b1cb8a9f4"
down_revision: str | Sequence[str] | None = "d41f0a8c7e21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_turns",
        sa.Column("turn_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'processing'"),
            nullable=False,
        ),
        sa.Column("response_data", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'completed', 'failed')",
            name=op.f("ck_conversation_turns_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["conversation_ownerships.thread_id"],
            name=op.f(
                "fk_conversation_turns_thread_id_conversation_ownerships"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name=op.f("fk_conversation_turns_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("turn_id", name=op.f("pk_conversation_turns")),
    )
    op.create_index(
        "ix_conversation_turns_thread_created",
        "conversation_turns",
        ["thread_id", "created_at"],
    )
    op.create_index(
        "uq_conversation_turns_active_thread",
        "conversation_turns",
        ["thread_id"],
        unique=True,
        postgresql_where=sa.text("status = 'processing'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_conversation_turns_active_thread",
        table_name="conversation_turns",
    )
    op.drop_index(
        "ix_conversation_turns_thread_created",
        table_name="conversation_turns",
    )
    op.drop_table("conversation_turns")
