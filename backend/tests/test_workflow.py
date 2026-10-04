from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.core.exceptions import AppException, ResourceNotFoundException
from app.graphs.conversation import ConversationNodes, build_conversation_graph
from app.schemas.conversations_intent import ConversationRequest, IntentAnalysisResult
from app.schemas.human_review import ResumeConversationRequest
from app.services.conversation import ConversationService


@pytest.fixture
def workflow(cv_profile, results):
    analyzer = SimpleNamespace(analyze=AsyncMock())
    services = {
        name: SimpleNamespace(**{method: AsyncMock(return_value=results[name])})
        for name, method in [
            ("cv_analysis", "analyze"), ("career_advice", "advise"),
            ("cover_letter", "generate"), ("job_search", "search"),
            ("job_matching", "match"),
        ]
    }
    nodes = ConversationNodes(
        analyzer=analyzer, cv_repository=SimpleNamespace(get=AsyncMock(return_value=cv_profile)),
        **{f"{name}_service": service for name, service in services.items()},
    )
    graph = build_conversation_graph(nodes, checkpointer=InMemorySaver())
    return SimpleNamespace(
        analyzer=analyzer, services=services, graph=graph,
        service=ConversationService(graph=graph),
    )


@pytest.mark.parametrize("intent", [
    "small_talk", "general_question", "out_of_scope", "cv_analysis",
    "career_advice", "job_search", "job_matching",
])
async def test_graph_routes_and_saves_history(workflow, intent):
    workflow.analyzer.analyze.return_value = IntentAnalysisResult(primary_intent=intent)
    request = ConversationRequest(message="Help with my career", cv_id="cv-a", job_description="Python developer")
    result = await workflow.service.process(request)
    assert result.status.value in {"completed", "routed"}
    history = await workflow.service.get_history(request.thread_id)
    assert [message.role for message in history.messages] == ["user", "assistant"]
    if intent in {"cv_analysis", "job_matching", "career_advice"}:
        assert getattr(result, f"{intent}_result") is not None


@pytest.mark.parametrize("missing", ["cv", "jd", "both"])
async def test_missing_context_clarifies(workflow, missing):
    workflow.analyzer.analyze.return_value = IntentAnalysisResult(
        primary_intent="job_matching", requires_cv=True, requires_jd=True,
    )
    result = await workflow.service.process(ConversationRequest(
        message="Match me", cv_id=None if missing in {"cv", "both"} else "cv-a",
        job_description=None if missing in {"jd", "both"} else "Python developer",
    ))
    assert result.status.value == "needs_clarification"
    workflow.services["job_matching"].match.assert_not_awaited()


@pytest.mark.parametrize("action", ["approve", "reject"])
async def test_real_interrupt_resume_and_repeat_guard(workflow, action):
    workflow.analyzer.analyze.return_value = IntentAnalysisResult(
        primary_intent="cover_letter", requires_cv=True, requires_jd=True,
    )
    request = ConversationRequest(message="Write a letter", cv_id="cv-a", job_description="Python developer")
    waiting = await workflow.service.process(request)
    assert waiting.status.value == "waiting_for_human"
    workflow.services["cover_letter"].generate.assert_not_awaited()
    history = await workflow.service.get_history(request.thread_id)
    assert history.pending_human_review is not None
    with pytest.raises(AppException) as exc:
        await workflow.service.process(request)
    assert exc.value.status_code == 409
    decision = ResumeConversationRequest(thread_id=request.thread_id, decision={"action": action})
    result = await workflow.service.resume(decision)
    assert result.status.value == "completed"
    if action == "approve":
        workflow.services["cover_letter"].generate.assert_awaited_once()
        assert result.cover_letter_result is not None
    else:
        workflow.services["cover_letter"].generate.assert_not_awaited()
        assert result.cover_letter_result is None
    assert (await workflow.service.get_history(request.thread_id)).pending_human_review is None
    with pytest.raises(AppException) as exc:
        await workflow.service.resume(decision)
    assert exc.value.status_code == 409


async def test_resume_unknown_thread(workflow):
    with pytest.raises(ResourceNotFoundException):
        await workflow.service.resume(ResumeConversationRequest(
            thread_id=uuid4(), decision={"action": "approve"},
        ))


async def test_multi_agent_chain(workflow):
    workflow.analyzer.analyze.return_value = IntentAnalysisResult(
        primary_intent="cv_analysis", secondary_intents=["career_advice", "cover_letter"],
        requires_cv=True, requires_jd=True,
    )
    request = ConversationRequest(message="Analyze, advise and write", cv_id="cv-a", job_description="Python developer")
    waiting = await workflow.service.process(request)
    assert waiting.status.value == "waiting_for_human"
    workflow.services["cv_analysis"].analyze.assert_awaited_once()
    workflow.services["career_advice"].advise.assert_awaited_once()
    workflow.services["cover_letter"].generate.assert_not_awaited()
    result = await workflow.service.resume(ResumeConversationRequest(
        thread_id=request.thread_id, decision={"action": "approve"},
    ))
    assert result.cover_letter_result is not None
    workflow.services["cv_analysis"].analyze.assert_awaited_once()
    workflow.services["cover_letter"].generate.assert_awaited_once()


async def test_threads_keep_separate_context(workflow):
    workflow.analyzer.analyze.return_value = IntentAnalysisResult(primary_intent="small_talk")
    first = ConversationRequest(message="First", cv_id="cv-a")
    second = ConversationRequest(message="Second")
    await workflow.service.process(first)
    await workflow.service.process(second)
    assert (await workflow.service.get_history(first.thread_id)).cv_id == "cv-a"
    assert (await workflow.service.get_history(second.thread_id)).cv_id is None
