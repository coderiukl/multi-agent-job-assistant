"""Ablation of the dense/sparse fusion mode (VECTOR_FUSION_MODE) on the
job_search_retrieval dataset.

The LLM search plan is generated ONCE per query and cached, so every fusion
variant ranks exactly the same plans: differences between variants come from
fusion only, not from LLM non-determinism. Two levels are measured:

* ``vector``      - the Qdrant ranking alone (``search_jobs`` top-k), i.e. the
                    direct effect of the fusion mode;
* ``end_to_end``  - the full hybrid service (PostgreSQL candidates + keyword +
                    freshness blending), i.e. what a user actually sees.

Each variant is compared with the ``dense`` baseline by a paired two-sided
sign-flip permutation test on the per-query scores.

Usage (inside the backend container, from /app):
    python -m evals.fusion_ablation
    python -m evals.fusion_ablation --limit 5                # smoke test
    python -m evals.fusion_ablation --linear-weights 0.5,0.7,0.9
    python -m evals.fusion_ablation --refresh-plans          # re-ask the LLM
"""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

import numpy as np  # noqa: E402

from app.core.exceptions import ExternalServiceException  # noqa: E402
from app.schemas.job_search import JobSearchPlan, JobSearchRequest  # noqa: E402
from app.schemas.job_search_context import JobSearchContext  # noqa: E402
from app.services.job_search import HybridJobSearchService  # noqa: E402
from evals.evaluators import (  # noqa: E402
    forbidden_jobs_absent,
    hit_at_k,
    mrr_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from evals.run_local_evaluation import call_evaluator, load_jsonl  # noqa: E402
from evals.runtime import (  # noqa: E402
    eval_metadata,
    get_job_search_agent,
    get_job_search_service,
)

EVALS_DIR = Path(__file__).resolve().parent
DATASET = EVALS_DIR / "datasets" / "job_search_retrieval.jsonl"
REPORTS_DIR = EVALS_DIR / "report"
PLANS_CACHE = REPORTS_DIR / "fusion-ablation-plans.json"

PAGE_SIZE = 10
BASELINE = "dense"
PERMUTATIONS = 10_000
EVALUATORS = [
    recall_at_k,
    precision_at_k,
    hit_at_k,
    mrr_at_k,
    ndcg_at_k,
    forbidden_jobs_absent,
]
TEST_METRICS = ("ndcg_at_k", "mrr_at_k", "recall_at_k", "hit_at_k")

_current_plan: contextvars.ContextVar[JobSearchPlan] = contextvars.ContextVar(
    "current_plan"
)


class CachedPlanAgent:
    """Stands in for JobSearchAgent: returns the plan set for the running task."""

    async def analyze(
        self, request: JobSearchRequest, *, context: JobSearchContext | None = None
    ) -> JobSearchPlan:
        return _current_plan.get()


def build_request(inputs: dict[str, Any]) -> JobSearchRequest:
    return JobSearchRequest.model_validate(
        {
            "query": inputs["query"],
            "filters": inputs.get("filters", {}),
            "sort": inputs.get("sort", "relevance"),
            "page": inputs.get("page", 1),
            "page_size": PAGE_SIZE,
        }
    )


def build_context(inputs: dict[str, Any]) -> JobSearchContext | None:
    value = inputs.get("candidate_context")
    return JobSearchContext.model_validate(value) if value else None


def case_id(example: dict[str, Any], index: int) -> str:
    return example.get("metadata", {}).get("case_id", f"example_{index:04d}")


async def load_or_create_plans(
    examples: list[dict[str, Any]], *, refresh: bool, max_concurrency: int
) -> dict[str, dict[str, Any]]:
    cached: dict[str, dict[str, Any]] = {}
    if PLANS_CACHE.exists() and not refresh:
        cached = json.loads(PLANS_CACHE.read_text(encoding="utf-8"))

    agent = get_job_search_agent()
    semaphore = asyncio.Semaphore(max_concurrency)
    missing = [
        (case_id(example, index), example)
        for index, example in enumerate(examples, start=1)
        if case_id(example, index) not in cached
    ]
    print(f"[plans] {len(examples) - len(missing)} cached, {len(missing)} to generate")

    async def generate(cid: str, example: dict[str, Any]) -> None:
        inputs = example["inputs"]
        request = build_request(inputs)
        async with semaphore:
            try:
                plan = await agent.analyze(request, context=build_context(inputs))
                source = "llm"
            except ExternalServiceException as exc:
                # Same fallback as HybridJobSearchService.search.
                plan = HybridJobSearchService._build_fallback_plan(request)
                source = f"fallback:{type(exc).__name__}"
        cached[cid] = {"source": source, "plan": plan.model_dump(mode="json")}
        print(f"[plans] {cid}: {source}")

    await asyncio.gather(*(generate(cid, example) for cid, example in missing))

    if missing:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        PLANS_CACHE.write_text(
            json.dumps(cached, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return cached


def ids_as_outputs(job_ids: list[str]) -> dict[str, Any]:
    return {"items": [{"job": {"job_id": job_id}} for job_id in job_ids]}


def score(outputs: dict[str, Any], reference: dict[str, Any], inputs: dict[str, Any]):
    return {
        result["key"]: result["score"]
        for result in (
            call_evaluator(
                evaluator,
                inputs=inputs,
                outputs=outputs,
                reference_outputs=reference,
            )
            for evaluator in EVALUATORS
        )
    }


async def run_variant(
    *,
    name: str,
    mode: str,
    dense_weight: float,
    examples: list[dict[str, Any]],
    plans: dict[str, dict[str, Any]],
    service: HybridJobSearchService,
    max_concurrency: int,
) -> dict[str, Any]:
    vector_index = service._vector_index
    # The index reads these per query; variants run one after another.
    vector_index._fusion_mode = mode
    vector_index._fusion_dense_weight = dense_weight

    semaphore = asyncio.Semaphore(max_concurrency)

    async def one(index: int, example: dict[str, Any]) -> dict[str, Any]:
        cid = case_id(example, index)
        inputs, reference = example["inputs"], example["outputs"]
        plan = JobSearchPlan.model_validate(plans[cid]["plan"])
        _current_plan.set(plan)
        request = build_request(inputs)

        async with semaphore:
            started = perf_counter()
            hits = await vector_index.search_jobs(
                query=plan.semantic_query, limit=PAGE_SIZE, filters=plan.filters
            )
            vector_latency = perf_counter() - started

            started = perf_counter()
            result = await service.search(request, context=build_context(inputs))
            e2e_latency = perf_counter() - started

        vector_ids = list(dict.fromkeys(hit.job_id for hit in hits))[:PAGE_SIZE]
        e2e_outputs = result.model_dump(mode="json")
        return {
            "case_id": cid,
            "language_style": example.get("metadata", {}).get("language_style"),
            "vector": {
                "job_ids": vector_ids,
                "scores": score(ids_as_outputs(vector_ids), reference, inputs),
                "latency_seconds": round(vector_latency, 4),
            },
            "end_to_end": {
                "job_ids": [item["job"]["job_id"] for item in e2e_outputs["items"]],
                "scores": score(e2e_outputs, reference, inputs),
                "latency_seconds": round(e2e_latency, 4),
            },
        }

    started = perf_counter()
    rows = await asyncio.gather(
        *(one(index, example) for index, example in enumerate(examples, start=1))
    )
    print(f"[{name}] {len(rows)} queries in {perf_counter() - started:.1f}s")
    return {"name": name, "mode": mode, "dense_weight": dense_weight, "rows": rows}


def per_query(variant: dict[str, Any], level: str, metric: str) -> np.ndarray:
    return np.array([row[level]["scores"][metric] for row in variant["rows"]])


def paired_permutation_p(a: np.ndarray, b: np.ndarray, seed: int = 0) -> float:
    """Two-sided sign-flip permutation test on the mean paired difference."""
    diff = a - b
    if not np.any(diff):
        return 1.0
    observed = abs(diff.mean())
    rng = np.random.default_rng(seed)
    signs = rng.choice((-1.0, 1.0), size=(PERMUTATIONS, diff.size))
    permuted = np.abs((signs * diff).mean(axis=1))
    return float((np.sum(permuted >= observed) + 1) / (PERMUTATIONS + 1))


def summarize(variants: list[dict[str, Any]]) -> dict[str, Any]:
    baseline = next(v for v in variants if v["name"] == BASELINE)
    metrics = [evaluator.__name__ for evaluator in EVALUATORS]
    styles = sorted({row["language_style"] or "?" for row in baseline["rows"]})
    summary: dict[str, Any] = {}

    for level in ("vector", "end_to_end"):
        summary[level] = {}
        for variant in variants:
            entry: dict[str, Any] = {
                "mean": {
                    metric: round(float(per_query(variant, level, metric).mean()), 4)
                    for metric in metrics
                },
                "latency_p50_seconds": round(
                    float(
                        np.median(
                            [row[level]["latency_seconds"] for row in variant["rows"]]
                        )
                    ),
                    4,
                ),
                "ndcg_by_language_style": {
                    style: round(
                        float(
                            np.mean(
                                [
                                    row[level]["scores"]["ndcg_at_k"]
                                    for row in variant["rows"]
                                    if (row["language_style"] or "?") == style
                                ]
                            )
                        ),
                        4,
                    )
                    for style in styles
                },
            }
            if variant["name"] != BASELINE:
                entry["vs_dense"] = {}
                for metric in TEST_METRICS:
                    a = per_query(variant, level, metric)
                    b = per_query(baseline, level, metric)
                    entry["vs_dense"][metric] = {
                        "delta": round(float((a - b).mean()), 4),
                        "wins": int(np.sum(a > b)),
                        "losses": int(np.sum(a < b)),
                        "p_value": round(paired_permutation_p(a, b), 4),
                    }
            summary[level][variant["name"]] = entry
    return summary


def print_tables(summary: dict[str, Any]) -> None:
    for level, variants in summary.items():
        print(f"\n### {level} (top-{PAGE_SIZE})\n")
        print(
            "| variant | nDCG | MRR | Recall | Hit | Prec "
            "| dNDCG vs dense (p) | p50 s |"
        )
        print("|---|---|---|---|---|---|---|---|")
        for name, entry in variants.items():
            m = entry["mean"]
            vs = entry.get("vs_dense", {}).get("ndcg_at_k")
            delta = f"{vs['delta']:+.4f} ({vs['p_value']:.3f})" if vs else "-"
            print(
                f"| {name} | {m['ndcg_at_k']:.4f} | {m['mrr_at_k']:.4f} | "
                f"{m['recall_at_k']:.4f} | {m['hit_at_k']:.4f} | "
                f"{m['precision_at_k']:.4f} | {delta} | "
                f"{entry['latency_p50_seconds']:.3f} |"
            )


async def async_main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-concurrency", type=int, default=2)
    parser.add_argument("--refresh-plans", action="store_true")
    parser.add_argument(
        "--linear-weights",
        default="0.7",
        help="Comma-separated dense weights for the linear mode (default 0.7).",
    )
    args = parser.parse_args()

    examples = load_jsonl(DATASET, args.limit)
    plans = await load_or_create_plans(
        examples, refresh=args.refresh_plans, max_concurrency=args.max_concurrency
    )

    base_service = get_job_search_service()
    service = HybridJobSearchService(
        agent=CachedPlanAgent(),  # type: ignore[arg-type]
        repository=base_service._repository,
        vector_index=base_service._vector_index,
        candidate_limit=base_service._candidate_limit,
    )
    original_mode = service._vector_index._fusion_mode
    original_weight = service._vector_index._fusion_dense_weight

    weights = [float(value) for value in args.linear_weights.split(",") if value]
    variant_specs = [
        ("dense", "dense", original_weight),
        ("sparse", "sparse", original_weight),
    ]
    variant_specs += [
        ("linear" if len(weights) == 1 else f"linear_w{weight:g}", "linear", weight)
        for weight in weights
    ]
    variant_specs.append(("rrf", "rrf", original_weight))

    # Warm-up: load the embedding model and open connections before timing.
    await service._vector_index.search_jobs(query="warm up", limit=1)

    started_at = datetime.now(UTC)
    variants = []
    try:
        for name, mode, weight in variant_specs:
            variants.append(
                await run_variant(
                    name=name,
                    mode=mode,
                    dense_weight=weight,
                    examples=examples,
                    plans=plans,
                    service=service,
                    max_concurrency=args.max_concurrency,
                )
            )
    finally:
        service._vector_index._fusion_mode = original_mode
        service._vector_index._fusion_dense_weight = original_weight

    summary = summarize(variants)
    plan_sources: dict[str, int] = {}
    for index, example in enumerate(examples, start=1):
        source = plans[case_id(example, index)]["source"].split(":")[0]
        plan_sources[source] = plan_sources.get(source, 0) + 1

    run_id = f"fusion-ablation-{started_at.strftime('%Y%m%dT%H%M%S%fZ')}"
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "dataset": DATASET.name,
        "examples": len(examples),
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "configuration": {
            "page_size": PAGE_SIZE,
            "baseline": BASELINE,
            "permutations": PERMUTATIONS,
            "collection": getattr(service._vector_index, "_collection_name", None),
            "plan_sources": plan_sources,
            "plans_cache": str(PLANS_CACHE),
        },
        "environment": eval_metadata(),
        "summary": summary,
        "variants": variants,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{run_id}.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"\nPlan sources: {plan_sources}")
    print_tables(summary)
    print(f"\nReport: {report_path}")


if __name__ == "__main__":
    asyncio.run(async_main())
