from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class JobModel(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True,)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    work_mode: Mapped[str] = mapped_column(String(50), nullable=False)
    seniority_level: Mapped[str] = mapped_column(String(50), nullable=False)
    skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    salary_period: Mapped[str] = mapped_column(String(50), nullable=False)
    salary_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_job_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    crawled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "source",
            "source_job_id",
            name="uq_jobs_source_source_job_id",
        ),
        CheckConstraint(
            (
                "salary_min IS NULL "
                "OR salary_max IS NULL "
                "OR salary_min <= salary_max"
            ),
            name="salary_range",
        ),
        CheckConstraint(
            (
                "(salary_min IS NULL AND salary_max IS NULL) "
                "OR salary_currency IS NOT NULL"
            ),
            name="salary_currency_required",
        ),
        Index(
            "ix_jobs_source_posted_at",
            "source",
            "posted_at",
        ),
        Index(
            "ix_jobs_work_mode",
            "work_mode",
        ),
        Index(
            "ix_jobs_employment_type",
            "employment_type",
        ),
        Index(
            "ix_jobs_seniority_level",
            "seniority_level",
        ),
        Index(
            "ix_jobs_content_hash",
            "content_hash",
        ),
    )