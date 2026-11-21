-- Completeness of each source's normalized jobs (shares in [0, 1]).
select
    source,
    count(*)                                                        as n_jobs,
    count(*) filter (where not is_expired)                          as n_active_jobs,
    round(avg((skill_count = 0)::int), 4)                           as pct_no_skills,
    round(avg((salary_mid is null)::int), 4)                        as pct_no_salary,
    round(avg((location is null)::int), 4)                          as pct_no_location,
    round(avg((seniority_level = 'unknown')::int), 4)               as pct_unknown_seniority,
    round(avg((work_mode = 'unknown')::int), 4)                     as pct_unknown_work_mode,
    round(avg((employment_type is null)::int), 4)                   as pct_no_employment_type,
    round(avg((posted_at is null)::int), 4)                         as pct_no_posted_at,
    round(avg(skill_count), 2)                                      as avg_skills_per_job,
    max(crawled_at)                                                 as last_crawled_at
from {{ ref('stg_jobs') }}
group by source
