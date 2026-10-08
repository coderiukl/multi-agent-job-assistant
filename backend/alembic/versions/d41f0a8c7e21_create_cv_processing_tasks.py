"""create cv processing tasks

Revision ID: d41f0a8c7e21
Revises: 9a899c1d39da
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d41f0a8c7e21"
down_revision: str | Sequence[str] | None = "9a899c1d39da"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cv_processing_tasks",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("cv_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_cv_processing_tasks_attempt_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "size_bytes > 0",
            name=op.f("ck_cv_processing_tasks_size_bytes_positive"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name=op.f("ck_cv_processing_tasks_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["cv_id"],
            ["cv_ownerships.cv_id"],
            name=op.f("fk_cv_processing_tasks_cv_id_cv_ownerships"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name=op.f("fk_cv_processing_tasks_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("task_id", name=op.f("pk_cv_processing_tasks")),
        sa.UniqueConstraint("cv_id", name=op.f("uq_cv_processing_tasks_cv_id")),
    )
    op.create_index(
        "ix_cv_processing_tasks_claim",
        "cv_processing_tasks",
        ["status", "available_at", "created_at"],
    )
    op.create_index(
        "ix_cv_processing_tasks_user_created",
        "cv_processing_tasks",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cv_processing_tasks_user_created",
        table_name="cv_processing_tasks",
    )
    op.drop_index(
        "ix_cv_processing_tasks_claim",
        table_name="cv_processing_tasks",
    )
    op.drop_table("cv_processing_tasks")
