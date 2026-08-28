from app.database.models import JobModel
from app.schemas.job import NormalizedJob


def job_model_to_schema(model: JobModel) -> NormalizedJob:
    return NormalizedJob(
        job_id=model.job_id,
        title=model.title,
        company=model.company,
        description=model.description,
        location=model.location,
        employment_type=model.employment_type,
        work_mode=model.work_mode,
        seniority_level=model.seniority_level,
        skills=list(model.skills or []),
        salary_min=model.salary_min,
        salary_max=model.salary_max,
        salary_period=model.salary_period,
        salary_currency=model.salary_currency,
        posted_at=model.posted_at,
        expires_at=model.expires_at,
        source=model.source,
        source_job_id=model.source_job_id,
        source_url=model.source_url,
        crawled_at=model.crawled_at,
        source_metadata=dict(
            model.source_metadata or {}
        ),
        content_hash=model.content_hash,
    )