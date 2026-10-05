import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langsmith import Client

from app.core.config import get_settings
from app.llm.factory import LLMFactory
from app.prompts.intent_analysis import INTENT_ANALYSIS_SYSTEM_PROMPT
from app.schemas.conversations_intent import IntentAnalysisInput
from app.services.conversation.intent_analyzer import ConversationIntentAnalyzer

DATASET_NAME = "mjaa-intent-smoke-v1"


def make_example(
    message: str,
    intent: str,
    *,
    has_cv: bool = False,
    has_jd: bool = False,
    requires_cv: bool = False,
    requires_jd: bool = False,
    needs_clarification: bool = False,
    secondary_intents: tuple[str, ...] = (),
    history: str = "No previous conversation.",
) -> dict[str, Any]:
    return {
        "inputs": {
            "message": message,
            "has_cv": has_cv,
            "has_jd": has_jd,
            "conversation_history": history,
        },
        "outputs": {
            "primary_intent": intent,
            "secondary_intents": list(secondary_intents),
            "requires_cv": requires_cv,
            "requires_jd": requires_jd,
            "needs_clarification": needs_clarification,
        },
    }


EXAMPLES = [
    make_example("Xin chào bạn!", "small_talk"),
    make_example("Hướng dẫn tôi nấu canh chua.", "out_of_scope"),
    make_example(
        "Nhà tuyển dụng thường hỏi gì trong buổi phỏng vấn?",
        "general_question",
    ),
    make_example(
        "Tìm việc thực tập Data Analyst ở TP.HCM.",
        "job_search",
    ),
    make_example(
        "Tôi muốn trở thành Data Engineer, nên học những kỹ năng nào?",
        "career_advice",
    ),
    make_example(
        "Phân tích CV đính kèm và nhận xét các điểm cần cải thiện.",
        "cv_analysis",
        has_cv=True,
        requires_cv=True,
    ),
    make_example(
        "Phân tích CV của tôi.",
        "cv_analysis",
        requires_cv=True,
        needs_clarification=True,
    ),
    make_example(
        "So sánh CV của tôi với JD này.",
        "job_matching",
        has_cv=True,
        has_jd=True,
        requires_cv=True,
        requires_jd=True,
    ),
    make_example(
        "So sánh CV của tôi với JD.",
        "job_matching",
        has_cv=True,
        requires_cv=True,
        requires_jd=True,
        needs_clarification=True,
    ),
    make_example(
        "Viết thư ứng tuyển dựa trên CV và JD đính kèm.",
        "cover_letter",
        has_cv=True,
        has_jd=True,
        requires_cv=True,
        requires_jd=True,
    ),
    make_example(
        "Tôi cần bạn hỗ trợ chuyện công việc nhưng chưa biết yêu cầu gì.",
        "clarification",
        needs_clarification=True,
    ),
    make_example(
        "Tìm việc phù hợp với CV và gợi ý kỹ năng tôi cần cải thiện.",
        "job_search",
        has_cv=True,
        requires_cv=True,
        secondary_intents=("job_matching", "career_advice"),
    ),
    make_example(
        "Chuyển sang tìm việc tương tự ở Hà Nội.",
        "job_search",
        history=(
            "User: Tìm việc thực tập Data Analyst ở TP.HCM.\n"
            "Assistant: Tôi sẽ tìm các vị trí thực tập Data Analyst ở TP.HCM."
        ),
    ),
]


def canonical_examples(examples: list[dict[str, Any]]) -> list[str]:
    return sorted(
        json.dumps(example, ensure_ascii=False, sort_keys=True)
        for example in examples
    )


def prepare_dataset(client: Client) -> None:
    if client.has_dataset(dataset_name=DATASET_NAME):
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
        existing = [
            {"inputs": example.inputs, "outputs": example.outputs}
            for example in client.list_examples(dataset_id=dataset.id)
        ]

        if canonical_examples(existing) != canonical_examples(EXAMPLES):
            raise RuntimeError(
                "Dataset trên LangSmith khác bộ dữ liệu trong code. "
                "Đổi DATASET_NAME sang phiên bản mới trước khi chạy."
            )

        print(f"Reusing dataset: {DATASET_NAME}")
        return

    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description="Small baseline dataset for the existing intent analyzer.",
    )
    client.create_examples(
        dataset_id=dataset.id,
        examples=EXAMPLES,
    )
    print(f"Created dataset: {DATASET_NAME}")


def intent_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    return {
        "key": "intent_correct",
        "score": int(
            outputs.get("primary_intent")
            == reference_outputs["primary_intent"]
        ),
    }


def secondary_intents_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    return {
        "key": "secondary_intents_correct",
        "score": int(
            set(outputs.get("secondary_intents", []))
            == set(reference_outputs["secondary_intents"])
        ),
    }


def requirements_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    fields = ("requires_cv", "requires_jd", "needs_clarification")

    return {
        "key": "requirements_correct",
        "score": int(
            all(
                outputs.get(field) == reference_outputs[field]
                for field in fields
            )
        ),
    }


async def main() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    load_dotenv(backend_dir / ".env", override=False)

    settings = get_settings()

    if not settings.langsmith_api_key:
        raise RuntimeError("LANGSMITH_API_KEY is missing.")

    if not settings.langsmith_tracing:
        raise RuntimeError("Set LANGSMITH_TRACING=true before running.")

    llm = LLMFactory.create_chat_model(settings)
    analyzer = ConversationIntentAnalyzer(llm)
    client = Client()

    # Dataset APIs are synchronous; run them outside the event loop.
    await asyncio.to_thread(prepare_dataset, client)

    async def target(inputs: dict[str, Any]) -> dict[str, Any]:
        input_data = IntentAnalysisInput.model_validate(inputs)
        result = await analyzer.analyze(input_data)
        return result.model_dump(mode="json")

    prompt_hash = hashlib.sha256(
        INTENT_ANALYSIS_SYSTEM_PROMPT.encode("utf-8")
    ).hexdigest()[:12]

    results = await client.aevaluate(
        target,
        data=DATASET_NAME,
        evaluators=[
            intent_correct,
            secondary_intents_correct,
            requirements_correct,
        ],
        experiment_prefix="intent-baseline",
        max_concurrency=1,
        num_repetitions=1,
        metadata={
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "prompt_hash": prompt_hash,
            "code_version": os.getenv("EVAL_CODE_VERSION", "local"),
            "dataset_version": DATASET_NAME,
        },
    )

    completed = 0
    failed = 0

    async for row in results:
        completed += 1
        if row["run"].error:
            failed += 1

    print(f"Finished: {completed} examples; failed runs: {failed}")
    print("Open the experiment link printed by LangSmith.")
    print("Inspect both evaluator scores and run errors.")


if __name__ == "__main__":
    asyncio.run(main())