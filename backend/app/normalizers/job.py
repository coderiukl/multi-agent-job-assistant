import hashlib
import json
from typing import Any

from app.normalizers.skills import SkillTaxonomy, get_skill_taxonomy
from app.schemas.job import JobCandidate, NormalizedJob


class JobNormalizer:
    def __init__(self, taxonomy: SkillTaxonomy | None = None) -> None:
        self._taxonomy = taxonomy or get_skill_taxonomy()

    def normalize(self, candidate: JobCandidate) -> NormalizedJob:
        candidate = self._normalize_skills(candidate)
        job_id = self._build_job_id(candidate)
        content_hash = self._build_content_hash(candidate)

        payload = candidate.model_dump()

        return NormalizedJob.model_validate(
            {
                **payload,
                "job_id": job_id,
                "content_hash": content_hash,
            }
        )

    def _normalize_skills(self, candidate: JobCandidate) -> JobCandidate:
        """Canonical skills; categories and taxonomy bookkeeping in metadata.

        Mappers whose source field is a job category (not a skill list) pass
        it as ``source_metadata["job_categories"]``.
        """
        metadata = dict(candidate.source_metadata)
        result = self._taxonomy.normalize(
            candidate.skills,
            text=f"{candidate.title}\n{candidate.description}",
            categories=list(metadata.get("job_categories") or []),
        )
        metadata.update(
            {
                "job_categories": result.categories,
                "raw_skills": list(candidate.skills),
                "unmapped_skills": result.unmapped,
                "skill_taxonomy_version": self._taxonomy.version,
            }
        )

        return candidate.model_copy(
            update={
                "skills": result.skills,
                "source_metadata": metadata,
            }
        )

    @staticmethod
    def _build_job_id(candidate: JobCandidate) -> str:
        identity = {
            "source": candidate.source.casefold(),
            "source_job_id": candidate.source_job_id,
        }

        return JobNormalizer._hash_payload(identity)

    def _build_content_hash(self, candidate: JobCandidate) -> str:
        content = candidate.model_dump(
            mode="json",
            exclude={
                "source",
                "source_job_id",
                "source_url",
                "crawled_at",
                "source_metadata",
            },
        )
        # A taxonomy change must change the hash, otherwise upsert_many and
        # the vector index treat re-normalized jobs as unchanged.
        content["skill_taxonomy_version"] = self._taxonomy.version
        content["job_categories"] = candidate.source_metadata.get("job_categories", [])

        return JobNormalizer._hash_payload(content)

    @staticmethod
    def _hash_payload(payload: dict[str, Any]) -> str:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        return hashlib.sha256(serialized.encode('utf-8')).hexdigest()
