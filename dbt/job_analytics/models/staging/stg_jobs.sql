-- One row per normalized job, typed and with derived analytics flags.
select
    job_id,
    lower(source)                                               as source,
    source_job_id,
    title,
    company,
    location,
    employment_type,
    work_mode,
    seniority_level,
    skills,
    jsonb_array_length(skills)                                  as skill_count,
    salary_min,
    salary_max,
    salary_currency,
    salary_period,
    case
        when salary_min is null and salary_max is null then null
        else (coalesce(salary_min, salary_max) + coalesce(salary_max, salary_min)) / 2.0
    end                                                         as salary_mid,
    posted_at,
    expires_at,
    crawled_at,
    created_at,
    updated_at,
    coalesce(expires_at < now(), false)                         as is_expired,
    source_metadata -> 'unmapped_skills'                        as unmapped_skills,
    source_metadata ->> 'skill_taxonomy_version'                as skill_taxonomy_version
from {{ source('app', 'jobs') }}
