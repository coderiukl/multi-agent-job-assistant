"""add CV retention deadline

Revision ID: b76f3a29c1de
Revises: e52b1cb8a9f4
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b76f3a29c1de"
down_revision: str | Sequence[str] | None = "e52b1cb8a9f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cv_ownerships",
        sa.Column(
            "retention_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE cv_ownerships "
        "SET retention_expires_at = created_at + INTERVAL '90 days' "
        "WHERE retention_expires_at IS NULL"
    )
    op.alter_column(
        "cv_ownerships",
        "retention_expires_at",
        nullable=False,
    )
    op.create_index(
        "ix_cv_ownerships_retention_expires_at",
        "cv_ownerships",
        ["retention_expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cv_ownerships_retention_expires_at",
        table_name="cv_ownerships",
    )
    op.drop_column("cv_ownerships", "retention_expires_at")
