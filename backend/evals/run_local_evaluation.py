from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

# These assignments intentionally happen before importing application services.
# They guarantee that a local evaluation cannot create LangSmith traces even if
# tracing is enabled in the developer's .env file.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from evals.evaluators import (  # noqa: E402
    INTENT_EVALUATORS,
    JOB_MATCHING_EVALUATORS,
    JOB_SEARCH_PLAN_EVALUATORS,
    JOB_SEARCH_RETRIEVAL_EVALUATORS,
)
from evals.runtime import eval_metadata  # noqa: E402
from evals.targets import (  # noqa: E402
    intent_analysis_target,
    job_matching_target,
    job_search_plan_target,
    job_search_retrieval_target,
)

EVALS_DIR = Path(__file__).resolve().parent
DATASETS_DIR = EVALS_DIR / "datasets"
REPORTS_DIR = EVALS_DIR / "report"

SUITES: dict[str, dict[str, Any]] = {
    "intent": {
        "dataset": DATASETS_DIR / "intent_analysis.jsonl",
        "target": intent_analysis_target,
        "evaluators": INTENT_EVALUATORS,
    },
    "search-plan": {
        "dataset": DATASETS_DIR / "job_search_plan.jsonl",
        "target": job_search_plan_target,
        "evaluators": JOB_SEARCH_PLAN_EVALUATORS,
    },
    "search-retrieval": {
        "dataset": DATASETS_DIR / "job_search_retrieval.jsonl",
        "target": job_search_retrieval_target,
        "evaluators": JOB_SEARCH_RETRIEVAL_EVALUATORS,
    },
    "matching": {
        "dataset": DATASETS_DIR / "job_matching.jsonl",
        "target": job_matching_target,
        "evaluators": JOB_MATCHING_EVALUATORS,
    },
}


def load_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    """Load and validate examples from a JSON Lines dataset."""
    examples: list[dict[str, Any]] = []

    with path.open(encoding="utf-8") as dataset_file:
        for line_number, raw_line in enumerate(dataset_file, start=1):
            if limit is not None and len(examples) >= limit:
                break

            line = raw_line.strip()
            if not line:
                continue

            try:
                example = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in {path} at line {line_number}: {exc.msg}"
                ) from exc

            if not isinstance(example, dict):
                raise ValueError(f"Expected an object in {path} at line {line_number}")
            if not isinstance(example.get("inputs"), dict):
                raise ValueError(f"Missing 'inputs' object at {path}:{line_number}")
            if not isinstance(example.get("outputs"), dict):
                raise ValueError(f"Missing 'outputs' object at {path}:{line_number}")

            examples.append(example)

    if not examples:
        raise ValueError(f"Dataset is empty: {path}")

    return examples


def call_evaluator(
    evaluator: Callable[..., dict[str, Any]],
    *,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    """Call an existing evaluator with only the arguments it declares."""
    available = {
        "inputs": inputs,
        "outputs": outputs,
        "reference_outputs": reference_outputs,
    }
    parameters = inspect.signature(evaluator).parameters
    kwargs = {name: available[name] for name in parameters if name in available}
    result = evaluator(**kwargs)

    if not isinstance(result, dict) or "key" not in result or "score" not in result:
        raise ValueError(f"Evaluator {evaluator.__name__} returned an invalid result")

    return {"key": str(result["key"]), "score": float(result["score"])}


async def evaluate_example(
    index: int,
    example: dict[str, Any],
    target: Callable[..., Any],
    evaluators: list[Callable[..., dict[str, Any]]],
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    inputs = example["inputs"]
    reference_outputs = example["outputs"]
    metadata = example.get("metadata", {})
    started = perf_counter()

    result: dict[str, Any] = {
        "index": index,
        "case_id": metadata.get("case_id", f"example_{index:04d}"),
        "status": "failed",
        "metadata": metadata,
        "inputs": inputs,
        "reference_outputs": reference_outputs,
        "outputs": None,
        "scores": [],
        "latency_seconds": 0.0,
        "error": None,
    }

    try:
        async with semaphore:
            outputs = await target(inputs)

        if not isinstance(outputs, dict):
            raise TypeError(f"Target returned {type(outputs).__name__}, expected dict")

        result["outputs"] = outputs
        scores = [
            call_evaluator(
                evaluator,
                inputs=inputs,
                outputs=outputs,
                reference_outputs=reference_outputs,
            )
            for evaluator in evaluators
        ]
        result.update(status="completed", scores=scores)
    except Exception as exc:  # Keep the rest of the dataset running.
        result["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
    finally:
        result["latency_seconds"] = round(perf_counter() - started, 6)

    return result


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    metric_values: dict[str, list[float]] = {}
    completed = 0

    for result in results:
        if result["status"] == "completed":
            completed += 1
        for score in result["scores"]:
            metric_values.setdefault(score["key"], []).append(score["score"])

    metrics = {
        key: {
            "count": len(values),
            "mean": round(sum(values) / len(values), 6),
            "pass_rate": round(sum(value >= 1.0 for value in values) / len(values), 6),
            "min": min(values),
            "max": max(values),
        }
        for key, values in sorted(metric_values.items())
    }
    all_scores = [value for values in metric_values.values() for value in values]

    return {
        "examples_total": len(results),
        "examples_completed": completed,
        "examples_failed": len(results) - completed,
        "mean_score": (
            round(sum(all_scores) / len(all_scores), 6) if all_scores else None
        ),
        "metrics": metrics,
    }


async def run_suite(
    suite_name: str,
    *,
    max_concurrency: int,
    limit: int | None,
) -> Path:
    suite = SUITES[suite_name]
    dataset_path: Path = suite["dataset"]
    examples = load_jsonl(dataset_path, limit)
    semaphore = asyncio.Semaphore(max_concurrency)
    started_at = datetime.now(UTC)

    print(f"\n[{suite_name}] Running {len(examples)} examples from {dataset_path.name}")
    tasks = [
        asyncio.create_task(
            evaluate_example(
                index,
                example,
                suite["target"],
                suite["evaluators"],
                semaphore,
            )
        )
        for index, example in enumerate(examples, start=1)
    ]

    results: list[dict[str, Any]] = []
    for completed_count, task in enumerate(asyncio.as_completed(tasks), start=1):
        result = await task
        results.append(result)
        marker = "OK" if result["status"] == "completed" else "ERROR"
        print(
            f"[{suite_name}] {completed_count}/{len(tasks)} "
            f"{result['case_id']}: {marker}"
        )

    results.sort(key=lambda item: item["index"])
    completed_at = datetime.now(UTC)
    summary = summarize(results)
    report = {
        "schema_version": 1,
        "run_id": f"{suite_name}-{started_at.strftime('%Y%m%dT%H%M%S%fZ')}",
        "suite": suite_name,
        "dataset": {
            "name": dataset_path.name,
            "path": str(dataset_path),
        },
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_seconds": round((completed_at - started_at).total_seconds(), 6),
        "configuration": {
            "max_concurrency": max_concurrency,
            "limit": limit,
            "langsmith_tracing": False,
        },
        "environment": eval_metadata(),
        "summary": summary,
        "results": results,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{report['run_id']}.json"
    with report_path.open("w", encoding="utf-8") as report_file:
        json.dump(report, report_file, ensure_ascii=False, indent=2)
        report_file.write("\n")

    print(
        f"[{suite_name}] Done: {summary['examples_completed']} completed, "
        f"{summary['examples_failed']} failed, mean score={summary['mean_score']}"
    )
    print(f"[{suite_name}] Report: {report_path}")
    return report_path


def choose_suite() -> str:
    choices = [*SUITES, "all"]
    print("Select a local evaluation dataset:")
    for index, name in enumerate(choices, start=1):
        if name == "all":
            label = "all datasets"
        else:
            label = f"{name} ({SUITES[name]['dataset'].name})"
        print(f"  {index}. {label}")

    while True:
        try:
            answer = input(f"Enter 1-{len(choices)}: ").strip()
        except EOFError as exc:
            raise SystemExit(
                "No interactive input available. Pass a dataset name, for example: "
                "python -m evals.run_local_evaluation intent"
            ) from exc

        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1]
        if answer in choices:
            return answer
        print("Invalid choice. Try again.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run evaluation locally and write JSON reports to evals/report/."
    )
    parser.add_argument(
        "suite",
        nargs="?",
        choices=[*SUITES, "all"],
        help="Dataset suite. Omit this argument to use the interactive selector.",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=2,
        help="Maximum target calls running at once (default: 2).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Run only the first N examples (useful for a quick smoke test).",
    )
    args = parser.parse_args()

    if args.max_concurrency < 1:
        parser.error("--max-concurrency must be at least 1")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    return args


async def async_main() -> None:
    args = parse_args()
    selected = args.suite or choose_suite()
    suite_names = list(SUITES) if selected == "all" else [selected]

    for suite_name in suite_names:
        await run_suite(
            suite_name,
            max_concurrency=args.max_concurrency,
            limit=args.limit,
        )


if __name__ == "__main__":
    asyncio.run(async_main())
