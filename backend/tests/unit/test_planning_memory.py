"""Pure-function tests for workflow planning, routing and memory helpers."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.graphs.conversation.planning import collect_missing_initial_inputs, create_workflow_plan
from app.graphs.conversation.workflow import advance_workflow
from app.memory.history import build_contextual_user_message, format_conversation_history
from app.schemas.conversation import RequiredInput
from app.schemas.conversation_search_context import (
    ConversationSearchContext,
    SearchContextPatch,
    apply_search_context_patch,
    split_search_locations,
)
from app.schemas.conversations_intent import ConversationIntent as I
from app.schemas.workflow import WorkflowStep as S
from app.schemas.workflow import WorkflowType as T
from tests.conftest import intent


@pytest.mark.parametrize(("intents", "workflow_type", "steps"), [
    ((I.SMALL_TALK,), T.SINGLE_AGENT, []),
    ((I.CV_ANALYSIS,), T.SINGLE_AGENT, [S.CV_ANALYSIS]),
    ((I.JOB_SEARCH,), T.JOB_DISCOVERY, [S.JOB_SEARCH]),
    ((I.JOB_MATCHING, I.JOB_SEARCH), T.JOB_RECOMMENDATION, [S.JOB_SEARCH, S.JOB_MATCHING]),
    ((I.COVER_LETTER, I.CV_ANALYSIS, I.JOB_SEARCH), T.FULL_CAREER,
     [S.CV_ANALYSIS, S.JOB_SEARCH, S.COVER_LETTER]),
])
def test_plan_01_workflow_plan(intents, workflow_type, steps):
    """TC-PLAN-01: intents -> workflow type and canonical step order."""
    plan = create_workflow_plan(intent(intents[0], *intents[1:]))
    assert (plan.workflow_type, plan.steps) == (workflow_type, steps)


@pytest.mark.parametrize(("steps", "has_cv", "has_jd", "missing"), [
    ([S.JOB_MATCHING], False, False, [RequiredInput.CV, RequiredInput.JOB_DESCRIPTION]),
    ([S.JOB_SEARCH, S.JOB_MATCHING], True, False, []),  # search produces the target
    ([S.CAREER_ADVICE], False, False, []),
    ([S.COVER_LETTER], True, False, [RequiredInput.JOB_DESCRIPTION]),
])
def test_plan_02_missing_inputs(steps, has_cv, has_jd, missing):
    """TC-PLAN-02: only inputs needed before the first executable step are required."""
    plan = create_workflow_plan(intent(I.SMALL_TALK)).model_copy(update={"steps": steps})
    assert collect_missing_initial_inputs(plan, has_cv=has_cv, has_jd=has_jd) == missing


def test_plan_03_advance_workflow():
    """TC-PLAN-03: steps advance in order and finish with COMPLETED."""
    plan = create_workflow_plan(intent(I.JOB_SEARCH, I.JOB_MATCHING))
    plan = advance_workflow(plan, S.JOB_SEARCH)
    assert plan.current_step == S.JOB_MATCHING
    plan = advance_workflow(plan, S.JOB_MATCHING)
    assert plan.current_step == S.COMPLETED and plan.completed_steps == plan.steps


def test_mem_01_history_window_and_current_message_dedup():
    """TC-MEM-01: last 6 messages, current message not duplicated, roles labelled."""
    messages = [HumanMessage(f"u{i}") if i % 2 == 0 else AIMessage(f"a{i}") for i in range(10)]
    messages.append(HumanMessage("current"))
    history = format_conversation_history(messages, current_message="current")
    assert history.splitlines() == ["User: u4", "Assistant: a5", "User: u6", "Assistant: a7",
                                    "User: u8", "Assistant: a9"]
    assert format_conversation_history([], current_message="x") == "No previous conversation."


def test_mem_02_long_message_keeps_saved_constraints():
    """TC-MEM-02 (BUG-025 fixed): a 2,000-char message (allowed by the API)
    keeps the saved search constraints; only the message is shortened, so the
    result still fits the 2,000-char agent inputs."""
    context = ConversationSearchContext(location="Hồ Chí Minh", seniority="intern")
    message = "Tìm việc " + "x" * 1991
    contextual = build_contextual_user_message(current_message=message,
                                               search_context=context)
    assert "Hồ Chí Minh" in contextual and "intern" in contextual
    assert len(contextual) <= 2000
    assert "Current user request:\nTìm việc xxx" in contextual
    assert contextual.endswith("…")


def test_mem_02b_short_message_is_unchanged():
    """TC-MEM-02b: no truncation when everything fits; no context -> raw message."""
    context = ConversationSearchContext(location="Hà Nội")
    contextual = build_contextual_user_message(current_message="Tìm việc Python",
                                               search_context=context)
    assert contextual.endswith("Current user request:\nTìm việc Python")
    assert build_contextual_user_message(current_message="x" * 2000) == "x" * 2000


def test_ctx_01_patch_and_location_split():
    """TC-CTX-01: patch merge/clear and multi-location parsing (vi/en separators)."""
    context = apply_search_context_patch(
        {"role": "Python", "location": "Hà Nội"},
        SearchContextPatch(location="HCM", clear_fields=["role"], work_mode="làm từ xa"))
    assert (context.role, context.location, context.work_mode.value) == (None, "HCM", "remote")
    assert split_search_locations("Hà Nội và HCM, hà nội; Đà Nẵng or Remote") == [
        "Hà Nội", "HCM", "Đà Nẵng", "Remote"]


def test_ctx_02_unknown_enum_labels_become_unknown():
    """TC-CTX-02: unrecognised seniority labels degrade to 'unknown', not 422."""
    assert ConversationSearchContext(seniority="principal").seniority.value == "unknown"
    assert ConversationSearchContext(seniority="Thực tập sinh").seniority.value == "intern"
