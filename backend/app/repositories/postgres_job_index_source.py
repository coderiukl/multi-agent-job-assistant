from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import StorageException
from app.database.models import JobModel
from app.database.session import JobSessionFactory
from app.repositories.job_mapping import job_model_to_schema
from app.schemas.job import NormalizedJob


class PostgresJobIndexSource:
    def __init__(self, session_factory: JobSessionFactory) -> None:
        self._session_factory = session_factory

    async def iter_batches(self, *, batch_size: int) -> AsyncIterator[list[NormalizedJob]]:
        if not 1 <= batch_size <= 1_000:
            raise ValueError(
                "batch_size must be between 1 and 1000."
            )

        cursor: str | None = None

        try:
            async with self._session_factory() as session:
                while True:
                    statement = (
                        select(JobModel)
                        .order_by(JobModel.job_id.asc())
                        .limit(batch_size)
                    )

                    if cursor is not None:
                        statement = statement.where(
                            JobModel.job_id > cursor
                        )

                    result = await session.scalars(statement)
                    models = list(result.all())

                    if not models:
                        break

                    yield [
                        job_model_to_schema(model)
                        for model in models
                    ]

                    cursor = models[-1].job_id

        except SQLAlchemyError as exc:
            raise StorageException(
                message=(
                    "Jobs could not be loaded from "
                    "PostgreSQL for indexing."
                ),
            ) from exc