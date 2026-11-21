"""create raw job records

Append-only raw layer (schema ``raw``) holding every distinct payload crawled
for a source job; the normalized ``jobs`` table can be rebuilt from it.

Revision ID: c3e1f7a9b2d4
Revises: b76f3a29c1de
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c3e1f7a9b2d4"
down_revision: str | Sequence[str] | None = "b76f3a29c1de"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS raw")
    op.create_table(
        "job_records",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("source_job_id", sa.String(length=255), nullable=False),
        sa.Column("batch_id", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("crawled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_job_records"),
        sa.UniqueConstraint(
            "source",
            "source_job_id",
            "payload_hash",
            name="uq_raw_job_records_version",
        ),
        schema="raw",
    )
    op.create_index(
        "ix_raw_job_records_latest",
        "job_records",
        ["source", "source_job_id", sa.text("crawled_at DESC")],
        unique=False,
        schema="raw",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_raw_job_records_latest",
        table_name="job_records",
        schema="raw",
    )
    op.drop_table("job_records", schema="raw")
    op.execute("DROP SCHEMA IF EXISTS raw")
