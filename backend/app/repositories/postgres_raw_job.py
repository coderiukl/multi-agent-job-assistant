"""PostgreSQL raw layer (``raw.job_records``) for crawled job payloads."""

import hashlib
import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import StorageException
from app.database.models import RawJobRecordModel
from app.database.session import JobSessionFactory
from app.schemas.job import RawJob

# asyncpg allows at most 32767 bind parameters per statement (9 per row).
INSERT_CHUNK_SIZE = 1_000


def build_payload_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _strip_nul(value: Any) -> Any:
    """PostgreSQL JSONB cannot store U+0000 inside strings."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [_strip_nul(item) for item in value]
    if isinstance(value, dict):
        return {key: _strip_nul(item) for key, item in value.items()}
    return value


class PostgresRawJobRepository:
    def __init__(self, session_factory: JobSessionFactory) -> None:
        self._session_factory = session_factory

    async def save_raw_records(
        self,
        *,
        batch_id: str,
        jobs: Sequence[RawJob],
    ) -> int:
        """Insert new payload versions; returns how many rows were added."""
        rows = self._build_rows(batch_id=batch_id, jobs=jobs)

        if not rows:
            return 0

        inserted = 0

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    for start in range(0, len(rows), INSERT_CHUNK_SIZE):
                        statement = (
                            insert(RawJobRecordModel)
                            .values(rows[start : start + INSERT_CHUNK_SIZE])
                            .on_conflict_do_nothing(
                                constraint="uq_raw_job_records_version",
                            )
                            .returning(RawJobRecordModel.id)
                        )
                        result = await session.execute(statement)
                        inserted += len(result.fetchall())

        except SQLAlchemyError as exc:
            raise StorageException(
                message="Raw job payloads could not be stored in PostgreSQL.",
            ) from exc

        return inserted

    async def iter_latest_records(
        self,
        *,
        source: str | None = None,
        batch_size: int = 500,
    ) -> AsyncIterator[list[RawJob]]:
        """Yield the newest payload of every source job, in key order."""
        if not 1 <= batch_size <= 5_000:
            raise ValueError("batch_size must be between 1 and 5000.")

        after: tuple[str, str] | None = None

        while True:
            statement = (
                select(
                    RawJobRecordModel.source,
                    RawJobRecordModel.source_job_id,
                    RawJobRecordModel.source_url,
                    RawJobRecordModel.payload,
                    RawJobRecordModel.crawled_at,
                )
                .distinct(
                    RawJobRecordModel.source,
                    RawJobRecordModel.source_job_id,
                )
                .order_by(
                    RawJobRecordModel.source,
                    RawJobRecordModel.source_job_id,
                    RawJobRecordModel.crawled_at.desc(),
                    RawJobRecordModel.id.desc(),
                )
                .limit(batch_size)
            )

            if source is not None:
                statement = statement.where(
                    RawJobRecordModel.source == source.casefold()
                )

            if after is not None:
                statement = statement.where(
                    tuple_(
                        RawJobRecordModel.source,
                        RawJobRecordModel.source_job_id,
                    )
                    > tuple_(*after)
                )

            try:
                async with self._session_factory() as session:
                    rows = (await session.execute(statement)).all()
            except SQLAlchemyError as exc:
                raise StorageException(
                    message="Raw job payloads could not be read from PostgreSQL.",
                ) from exc

            if not rows:
                return

            yield [
                RawJob(
                    source=row.source,
                    source_job_id=row.source_job_id,
                    source_url=row.source_url,
                    payload=row.payload,
                    crawled_at=row.crawled_at,
                )
                for row in rows
            ]

            if len(rows) < batch_size:
                return

            after = (rows[-1].source, rows[-1].source_job_id)

    @staticmethod
    def _build_rows(
        *,
        batch_id: str,
        jobs: Sequence[RawJob],
    ) -> list[dict[str, Any]]:
        rows: dict[tuple[str, str, str], dict[str, Any]] = {}

        for job in jobs:
            payload = _strip_nul(job.payload)
            payload_hash = build_payload_hash(payload)
            source = job.source.casefold()
            # The same payload twice in one batch would violate the unique
            # constraint inside a single INSERT statement.
            rows[(source, job.source_job_id, payload_hash)] = {
                "source": source,
                "source_job_id": job.source_job_id,
                "batch_id": batch_id,
                "source_url": str(job.source_url),
                "payload": payload,
                "payload_hash": payload_hash,
                "crawled_at": job.crawled_at,
            }

        return list(rows.values())
