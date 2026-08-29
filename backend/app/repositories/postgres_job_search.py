from collections.abc import Sequence

from sqlalchemy import (
    Select,
    Text,
    cast,
    func,
    or_,
    select,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.elements import ColumnElement

from app.core.exceptions import StorageException
from app.database.models import JobModel
from app.database.session import JobSessionFactory
from app.schemas.job import (
    NormalizedJob,
    SeniorityLevel,
)
from app.schemas.job_search import (
    JobSearchPage,
    JobSearchPlan,
    JobSearchSort,
)
from app.repositories.job_mapping import job_model_to_schema


class PostgresJobSearchRepository:
    def __init__(self, session_factory: JobSessionFactory) -> None:
        self._session_factory = session_factory

    async def search(self, *, plan: JobSearchPlan, page: int, page_size: int) -> JobSearchPage:
        self._validate_pagination(
            page=page,
            page_size=page_size,
        )

        try:
            async with self._session_factory() as session:
                filtered_statement = self._build_filtered_statement(
                    plan
                )

                count_statement = (
                    select(func.count())
                    .select_from(filtered_statement.subquery())
                )

                total = int(
                    await session.scalar(count_statement) or 0
                )

                search_statement = self._apply_sorting(
                    statement=filtered_statement,
                    plan=plan,
                )

                search_statement = search_statement.offset(
                    (page - 1) * page_size
                ).limit(page_size)

                result = await session.scalars(search_statement)
                models = result.all()

        except SQLAlchemyError as exc:
            raise StorageException(
                message=(
                    "Jobs could not be searched in PostgreSQL."
                )
            ) from exc

        return JobSearchPage(
            total=total,
            page=page,
            page_size=page_size,
            jobs=[
                job_model_to_schema(model)
                for model in models
            ],
        )

    async def search_candidates(self, *, plan: JobSearchPlan, limit: int) -> list[NormalizedJob]:
        ...

    async def get_by_ids(self, *, job_ids: Sequence[str], plan: JobSearchPlan) -> list[NormalizedJob]:
        ...

    def _build_filtered_statement(self, plan: JobSearchPlan) -> Select[tuple[JobModel]]:
        statement = select(JobModel)
        conditions = self._build_conditions(plan)

        if conditions:
            statement = statement.where(*conditions)

        return statement

    def _build_conditions(self, plan: JobSearchPlan) -> list[ColumnElement[bool]]:
        filters = plan.filters
        conditions: list[ColumnElement[bool]] = []

        if not filters.include_expired:
            conditions.append(
                or_(
                    JobModel.expires_at.is_(None),
                    JobModel.expires_at >= func.now(),
                )
            )

        if filters.locations:
            location_conditions = [
                JobModel.location.ilike(
                    self._contains_pattern(location),
                    escape="\\",
                )
                for location in filters.locations
            ]

            conditions.append(or_(*location_conditions))

        if filters.employment_types:
            conditions.append(
                JobModel.employment_type.in_(
                    [
                        employment_type.value
                        for employment_type
                        in filters.employment_types
                    ]
                )
            )

        if filters.work_modes:
            conditions.append(
                JobModel.work_mode.in_(
                    [
                        work_mode.value
                        for work_mode in filters.work_modes
                    ]
                )
            )

        if filters.seniority_levels:
            seniority_values = {
                seniority.value
                for seniority in filters.seniority_levels
            }

            seniority_values.add(SeniorityLevel.UNKNOWN.value)

            conditions.append(
                JobModel.seniority_level.in_(
                    sorted(seniority_values)
                )
            )

        if filters.skills:
            serialized_skills = cast(JobModel.skills, Text)

            skill_conditions = [
                serialized_skills.ilike(
                    self._contains_pattern(skill),
                    escape="\\",
                )
                for skill in filters.skills
            ]

            conditions.append(or_(*skill_conditions))

        if filters.salary_min is not None:
            maximum_available_salary = func.coalesce(
                JobModel.salary_max,
                JobModel.salary_min,
            )

            conditions.append(
                maximum_available_salary >= filters.salary_min
            )

        if filters.salary_currency is not None:
            conditions.append(
                JobModel.salary_currency
                == filters.salary_currency
            )

        if filters.posted_after is not None:
            conditions.append(
                JobModel.posted_at >= filters.posted_after
            )

        keyword_condition = self._build_keyword_condition(
            plan.keywords
        )

        if keyword_condition is not None:
            conditions.append(keyword_condition)

        return conditions

    def _build_keyword_condition(self, keywords: Sequence[str]) -> ColumnElement[bool] | None:
        if not keywords:
            return None

        serialized_skills = cast(JobModel.skills, Text)
        keyword_conditions: list[ColumnElement[bool]] = []

        for keyword in keywords:
            pattern = self._contains_pattern(keyword)

            keyword_conditions.extend(
                [
                    JobModel.title.ilike(
                        pattern,
                        escape="\\",
                    ),
                    JobModel.description.ilike(
                        pattern,
                        escape="\\",
                    ),
                    JobModel.company.ilike(
                        pattern,
                        escape="\\",
                    ),
                    serialized_skills.ilike(
                        pattern,
                        escape="\\",
                    ),
                ]
            )

        return or_(*keyword_conditions)

    @staticmethod
    def _apply_sorting(*, statement: Select[tuple[JobModel]], plan: JobSearchPlan) -> Select[tuple[JobModel]]:
        if plan.sort == JobSearchSort.NEWEST:
            return statement.order_by(
                JobModel.posted_at.desc().nullslast(),
                JobModel.crawled_at.desc(),
                JobModel.job_id.asc(),
            )

        return statement.order_by(
            JobModel.posted_at.desc().nullslast(),
            JobModel.crawled_at.desc(),
            JobModel.job_id.asc(),
        )

    @staticmethod
    def _contains_pattern(value: str) -> str:
        escaped = (
            value
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )

        return f"%{escaped}%"

    @staticmethod
    def _validate_pagination(*, page: int, page_size: int) -> None:
        if page < 1:
            raise ValueError("page must be greater than or equal to 1.")

        if not 1 <= page_size <= 50:
            raise ValueError(
                "page_size must be between 1 and 50."
            )