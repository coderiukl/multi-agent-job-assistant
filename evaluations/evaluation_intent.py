import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langsmith import Client, aevaluate
from langsmith.schemas import Example, Run

# 1. Project and Configuration

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
DATASET_PATH = ROOT_DIR / "evaluations" / "datasets" / "intent_dataset.json"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.dependencies import get_chat_model
from app.schemas.conversations_intent import ( 
    IntentAnalysisInput,
    IntentAnalysisResult,
)
from app.services.conversation.intent_analyzer import ConversationIntentAnalyzer

from evaluations.intent_metrics import score_intent  

logger = logging.getLogger(__name__)

DATASET_NAME = os.getenv(
    "INTENT_EVAL_DATASET",
    "intent-analysis-gold-v1",
)

EXPERIMENT_PREFIX = "intent-analysis-baseline"

# 2.Load and Validate dataset

def load_dataset() -> list[dict[str, Any]]:
    
    if not DATASET_PATH.is_file():
        raise FileNotFoundError(f"Intent dataset not found: {DATASET_PATH}")

    with DATASET_PATH.open("r", encoding="utf-8") as file:
        examples = json.load(file)

    if not isinstance(examples, list) or not examples:
        raise ValueError("Intent dataset must be a non-empty list.")

    seen_ids: set[str] = set()

    for item in examples:
        example_id = item["id"]

        if example_id in seen_ids:
            raise ValueError(f"Duplicate evaluation ID: {example_id}")

        seen_ids.add(example_id)

        IntentAnalysisInput.model_validate(item["inputs"])

        reference = item["reference_outputs"]

        required_fields = (
            "primary_intent",
            "secondary_intents",
            "requires_cv",
            "requires_jd",
            "needs_clarification",
        )

        for field in required_fields:
            if field not in reference:
                raise ValueError(f"{example_id}: missing reference {field}")

        IntentAnalysisResult.model_validate(
            {
                **reference,
                "confidence": 1.0,
            }
        )

    return examples

# 3. synchronize dataset to langsmith

def ensure_langsmith_dataset(client: Client, examples: list[dict[str, Any]]) -> str:
    
    if client.has_dataset(dataset_name=DATASET_NAME):
        logger.info(
            "Existing LangSmith dataset: %s",
            DATASET_NAME,
        )
        return DATASET_NAME

    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description=(
            "Human-reviewed Intent Analysis gold examples "
            "for Multi-Agent Job Assistant."
        ),
    )

    client.create_examples(
        dataset_id=dataset.id,
        inputs=[
            item["inputs"]
            for item in examples
        ],
        outputs=[
            item["reference_outputs"]
            for item in examples
        ],
        metadata=[
            {
                "case_id": item["id"],
                "category": item.get("category", "unknown"),
            }
            for item in examples
        ],
    )

    logger.info(
        "Created LangSmith dataset with %d examples.",
        len(examples),
    )

    return DATASET_NAME


# 4. Run

def build_intent_target():

    analyzer = ConversationIntentAnalyzer(llm=get_chat_model())

    async def target(inputs: dict[str, Any]) -> dict[str, Any]:
        validated_input = IntentAnalysisInput.model_validate(inputs)

        result = await analyzer.analyze(validated_input)

        return result.model_dump(mode="json")

    return target

# 5. Langsmith Evaluators

def intent_evaluator(run: Run, example: Example) -> list[dict[str, Any]]:
    
    if not run.outputs:
        raise ValueError("Intent run has no outputs.")

    if not example.outputs:
        raise ValueError("Gold example has no reference output.")

    scores = score_intent(
        prediction=run.outputs,
        reference=example.outputs,
    )

    visible_metrics = (
        "primary_accuracy",
        "secondary_exact_match",
        "secondary_f1_example",
        "requires_cv_accuracy",
        "requires_jd_accuracy",
        "clarification_accuracy",
        "all_fields_correct",
    )

    return [
        {
            "key": metric,
            "score": scores[metric],
        }
        for metric in visible_metrics
    ]

# 6. Execute Langsmith experiment

async def run_evaluation() -> None:
    
    load_dotenv(ROOT_DIR / ".env", override=False)
    load_dotenv(BACKEND_DIR / ".env", override=False)

    if not os.getenv("LANGSMITH_API_KEY"):
        raise RuntimeError("LANGSMITH_API_KEY is required to run evaluation.")

    examples = load_dataset()
    client = Client()

    dataset_name = ensure_langsmith_dataset(client, examples)

    target = build_intent_target()

    logger.info("Running Intent evaluation with %d local examples.", len(examples))

    results = await aevaluate(
        target,
        data=dataset_name,
        evaluators=[intent_evaluator],
        experiment_prefix=EXPERIMENT_PREFIX,
        max_concurrency=2,
        client=client,
        metadata={
            "component": "intent_analysis",
            "evaluation_version": "v1",
        },
    )

    # Consume results so execution completes and failures surface.
    completed = 0

    async for _ in results:
        completed += 1

    logger.info("Intent evaluation completed: %d cases.", completed)
    logger.info("Open LangSmith Experiments to review feedback.")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        asyncio.run(run_evaluation())
    except Exception:
        logger.exception("Intent evaluation failed.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
