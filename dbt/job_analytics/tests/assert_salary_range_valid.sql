-- Fails for jobs whose salary bounds are inverted or that have a salary
-- without a currency (mirrors the CHECK constraints of public.jobs).
select job_id, salary_min, salary_max, salary_currency
from {{ ref('stg_jobs') }}
where (salary_min is not null and salary_max is not null and salary_min > salary_max)
   or (salary_mid is not null and salary_currency is null)
