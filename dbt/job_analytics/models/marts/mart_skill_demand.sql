-- Share of active (non-expired) jobs requiring each skill, per seniority level
-- and overall ('all'). Feeds market insights / career advice.
with active_jobs as (
    select job_id, seniority_level
    from {{ ref('stg_jobs') }}
    where not is_expired
),

active_skills as (
    select s.job_id, s.skill, a.seniority_level
    from {{ ref('stg_job_skills') }} as s
    inner join active_jobs as a on a.job_id = s.job_id
),

by_level as (
    select seniority_level, skill, count(distinct job_id) as job_count
    from active_skills
    group by 1, 2

    union all

    select 'all' as seniority_level, skill, count(distinct job_id) as job_count
    from active_skills
    group by 2
),

totals as (
    select seniority_level, count(*) as total_jobs
    from active_jobs
    group by 1

    union all

    select 'all' as seniority_level, count(*) as total_jobs
    from active_jobs
)

select
    b.seniority_level,
    b.skill,
    b.job_count,
    t.total_jobs,
    round(100.0 * b.job_count / nullif(t.total_jobs, 0), 2)    as pct_of_jobs,
    rank() over (
        partition by b.seniority_level
        order by b.job_count desc
    )                                                           as demand_rank
from by_level as b
inner join totals as t on t.seniority_level = b.seniority_level
