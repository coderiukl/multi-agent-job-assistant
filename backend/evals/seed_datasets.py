import argparse
import json
from pathlib import Path
from typing import Any

from langsmith import Client

from evals.runtime import config_langsmith

DATASETS = {
    "intent": {
        "name": "job-assistant-intent-v1",
        "file": "intent_analysis.jsonl",
        "description": ("Golden dataset for conversation intent analysis."),
    },
    "search-plan": {
        "name": "job-assistant-search-plan-v1",
        "file": "job_search_plan.jsonl",
        "description": ("Golden dataset for JobSearchAgent plans."),
    },
    "search-retrieval": {
        "name": "job-assistant-search-retrieval-v1",
        "file": "job_search_retrieval.jsonl",
        "description": ("Golden dataset for hybrid job search retrieval and ranking."),
    },
    "matching": {
        "name": "job-assistant-matching-v1",
        "file": "job_matching.jsonl",
        "description": ("Synthetic and anonymized CV-job matching dataset."),
    },
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON at {path}:{line_number}") from exc

        if "inputs" not in record or "outputs" not in record:
            raise ValueError(f"{path}:{line_number} must contain inputs and outputs.")

        records.append(record)

    return records


def find_dataset(client: Client, dataset_name: str):
    datasets = list(
        client.list_datasets(
            dataset_name=dataset_name,
            limit=1,
        )
    )

    return datasets[0] if datasets else None


def seed_dataset(
    client: Client,
    *,
    dataset_name: str,
    description: str,
    dataset_file: Path,
) -> None:
    existing = find_dataset(client, dataset_name)

    if existing is not None:
        print(f"Dataset '{dataset_name}' already exists; skipping.")
        return

    records = load_jsonl(dataset_file)

    dataset = client.create_dataset(
        dataset_name=dataset_name,
        description=description,
    )

    client.create_examples(
        dataset_id=dataset.id,
        inputs=[record["inputs"] for record in records],
        outputs=[record["outputs"] for record in records],
        metadata=[record.get("metadata", {}) for record in records],
    )

    print(f"Created '{dataset_name}' with {len(records)} examples.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=[*DATASETS, "all"])
    args = parser.parse_args()

    config_langsmith()
    client = Client()

    selected = (
        DATASETS.items()
        if args.suite == "all"
        else [(args.suite, DATASETS[args.suite])]
    )

    datasets_directory = Path(__file__).parent / "datasets"

    for _, definition in selected:
        seed_dataset(
            client,
            dataset_name=definition["name"],
            description=definition["description"],
            dataset_file=(datasets_directory / definition["file"]),
        )


if __name__ == "__main__":
    main()
