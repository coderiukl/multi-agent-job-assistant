import hashlib
import json
from typing import Any

from app.schemas.job import JobCandidate, NormalizedJob

class JobNormalizer:
    def normalize(self, candidate: JobCandidate) -> NormalizedJob:
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

    @staticmethod
    def _build_job_id(candidate: JobCandidate) -> str:
        identity = {
            "source": candidate.source.casefold(),
            "source_job_id": candidate.source_job_id,
        }

        return JobNormalizer._hash_payload(identity)

    @staticmethod
    def _build_content_hash(candidate: JobCandidate) -> str:
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
    