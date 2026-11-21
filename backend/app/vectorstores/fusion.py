"""Fusion of dense (semantic) and sparse (lexical) BGE-M3 retrieval results.

Every mode returns scores in [0, 1] so they can replace the cosine score that
``JobSearchService`` blends with keyword/freshness scores (semantic weight 0.6):

* ``dense``  - dense cosine only (the previous behaviour).
* ``sparse`` - sparse score divided by the best sparse score of the query.
* ``linear`` - ``w * cosine + (1 - w) * sparse / best_sparse``; keeps the cosine
  scale, therefore the default.
* ``rrf``    - Reciprocal Rank Fusion (k = 60) divided by its ceiling (rank 1 in
  every non-empty list), i.e. a rank-based score.
"""

from collections.abc import Sequence
from typing import Literal

from app.schemas.job_search import JobVectorSearchHit

FusionMode = Literal["dense", "sparse", "linear", "rrf"]
FUSION_MODES: tuple[FusionMode, ...] = ("dense", "sparse", "linear", "rrf")
RRF_K = 60

ScoredIds = Sequence[tuple[str, float]]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _relative_to_best(hits: ScoredIds) -> dict[str, float]:
    best = max((score for _, score in hits), default=0.0)
    if best <= 0:
        return {job_id: 0.0 for job_id, _ in hits}
    return {job_id: score / best for job_id, score in hits}


def _first_score_per_id(hits: ScoredIds) -> dict[str, float]:
    scores: dict[str, float] = {}
    for job_id, score in hits:
        scores.setdefault(job_id, score)
    return scores


def fuse_hits(
    dense: ScoredIds,
    sparse: ScoredIds,
    *,
    mode: FusionMode,
    limit: int,
    dense_weight: float = 0.7,
) -> list[JobVectorSearchHit]:
    """Fuse two ranked hit lists (sorted by descending score)."""
    if mode not in FUSION_MODES:
        raise ValueError(f"Unsupported fusion mode: {mode!r}.")
    if limit < 1:
        return []
    if not 0.0 <= dense_weight <= 1.0:
        raise ValueError("dense_weight must be between 0 and 1.")

    if mode == "dense" or (not sparse and mode != "sparse"):
        scores = _first_score_per_id(dense)

    elif mode == "sparse":
        scores = _relative_to_best(sparse)

    elif mode == "rrf":
        lists = [hits for hits in (dense, sparse) if hits]
        raw: dict[str, float] = {}
        for hits in lists:
            seen: set[str] = set()
            rank = 0
            for job_id, _ in hits:
                if job_id in seen:
                    continue
                seen.add(job_id)
                rank += 1
                raw[job_id] = raw.get(job_id, 0.0) + 1.0 / (RRF_K + rank)
        ceiling = len(lists) / (RRF_K + 1)
        scores = {job_id: value / ceiling for job_id, value in raw.items()}

    else:  # linear
        dense_scores = _first_score_per_id(dense)
        sparse_scores = _relative_to_best(sparse)
        scores = {
            job_id: dense_weight * dense_scores.get(job_id, 0.0)
            + (1.0 - dense_weight) * sparse_scores.get(job_id, 0.0)
            for job_id in dense_scores.keys() | sparse_scores.keys()
        }

    ranked = sorted(
        scores.items(),
        key=lambda item: (-item[1], item[0]),
    )[:limit]

    # Pure dense results keep the raw cosine (it may be negative), exactly as
    # before fusion existed; fused scores are clamped to [0, 1].
    keep_raw = mode == "dense" or (not sparse and mode != "sparse")

    return [
        JobVectorSearchHit(
            job_id=job_id,
            score=max(-1.0, min(1.0, score)) if keep_raw else _clamp(score),
        )
        for job_id, score in ranked
    ]
