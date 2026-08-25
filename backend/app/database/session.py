from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


JobSessionFactory = async_sessionmaker[AsyncSession]


def create_job_database_engine(settings: Settings) -> AsyncEngine:
    database_url = settings.job_database_url

    if not database_url:
        raise ValueError(
            "JOB_DATABASE_URL is required when PostgreSQL "
            "job storage is enabled."
        )

    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError(
            "JOB_DATABASE_URL must use the "
            "postgresql+asyncpg:// driver."
        )

    return create_async_engine(
        database_url,
        echo=settings.job_database_echo,
        pool_pre_ping=True,
        pool_size=settings.job_database_pool_size,
        max_overflow=settings.job_database_max_overflow,
    )


def create_job_session_factory(engine: AsyncEngine) -> JobSessionFactory:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )