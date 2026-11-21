-- Salary quartiles of active jobs per seniority, currency and pay period.
-- Currencies/periods are never mixed; small groups are suppressed.
with salaried as (
    select seniority_level, salary_currency, salary_period, salary_mid
    from {{ ref('stg_jobs') }}
    where not is_expired
      and salary_mid is not null
      and salary_currency is not null
      and salary_period <> 'unknown'
)

select
    seniority_level,
    salary_currency,
    salary_period,
    count(*)                                                        as n_jobs,
    round(percentile_cont(0.25) within group (order by salary_mid)::numeric, 2) as p25,
    round(percentile_cont(0.50) within group (order by salary_mid)::numeric, 2) as p50,
    round(percentile_cont(0.75) within group (order by salary_mid)::numeric, 2) as p75
from salaried
group by 1, 2, 3
having count(*) >= {{ var('min_salary_sample') }}
