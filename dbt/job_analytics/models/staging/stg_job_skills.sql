-- One row per (job, skill). Skills are already canonical (skill taxonomy in
-- app/normalizers/skills.py), so grouping by name merges synonyms.
select
    j.job_id,
    j.source,
    j.seniority_level,
    j.work_mode,
    j.is_expired,
    trim(s.skill)               as skill,
    lower(trim(s.skill))        as skill_key
from {{ ref('stg_jobs') }} as j
cross join lateral jsonb_array_elements_text(j.skills) as s(skill)
where trim(s.skill) <> ''
