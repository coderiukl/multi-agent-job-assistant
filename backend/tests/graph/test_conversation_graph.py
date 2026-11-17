"""Multi-agent orchestration tests (Phase 3).

The real LangGraph StateGraph, ConversationNodes, ConversationService and
InMemorySaver checkpointer are used. Only the LLM-backed analyzer and the
business agents are replaced by deterministic fakes, so routing, state
transitions, memory and human-in-the-loop behaviour are exercised for real.

Tests marked ``xfail(strict=True)`` encode the *required* behaviour and fail
today because of a confirmed defect (see BUG_REPORT.md). If the defect is
fixed the test XPASSes and pytest reports it, so the marker must be removed.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.exceptions import AppException, ResourceNotFoundException
from app.schemas.conversation import ConversationRoute, ConversationStatus, RequiredInput
from app.schemas.conversations_intent import ConversationIntent as I
from app.schemas.workflow import WorkflowExecutionStatus, WorkflowType
from tests.conftest import GraphHarness, intent, make_job

JD = (
    "Backend Intern. Yêu cầu kỹ năng Python, FastAPI. "
    "Có kinh nghiệm với PostgreSQL là lợi thế."
)


# --------------------------------------------------------------------------
# Scenario 1 – CV analysis
# --------------------------------------------------------------------------
async def test_orc_01_cv_analysis_routes_to_cv_agent(harness: GraphHarness):
    """TC-ORC-01: 'Phân tích CV của tôi' + uploaded CV -> CV Analysis Agent."""
    harness.analyzer.on("phân tích cv", intent(I.CV_ANALYSIS))
    cv_id = harness.add_cv()

    response = await harness.send("Phân tích CV của tôi.", cv_id=cv_id)

    assert response.route == ConversationRoute.CV_ANALYSIS
    assert response.status == ConversationStatus.COMPLETED
    assert response.cv_analysis_result is not None
    assert len(harness.cv_analysis.inputs) == 1
    assert harness.cv_analysis.inputs[0].cv_profile.skills[0] == "Python"


async def test_orc_02_cv_analysis_without_cv_asks_for_upload(harness: GraphHarness):
    """TC-ORC-02: CV analysis without a CV -> clarification, agent not called."""
    harness.analyzer.on("phân tích cv", intent(I.CV_ANALYSIS))

    response = await harness.send("Phân tích CV của tôi.")

    assert response.status == ConversationStatus.NEEDS_CLARIFICATION
    assert response.missing_inputs == [RequiredInput.CV]
    assert harness.cv_analysis.inputs == []


async def test_orc_19_unknown_cv_id_returns_not_found(harness: GraphHarness):
    """TC-ORC-19: a cv_id that has no stored profile -> 404, no agent call."""
    harness.analyzer.on("phân tích", intent(I.CV_ANALYSIS))

    with pytest.raises(ResourceNotFoundException):
        await harness.send("Phân tích CV", cv_id="f" * 32)
    assert harness.cv_analysis.inputs == []


# --------------------------------------------------------------------------
# Scenario 2 – Job search + search context memory
# --------------------------------------------------------------------------
SEARCH_PATCH = {"role": "Python Backend", "location": "Hồ Chí Minh", "seniority": "intern"}


async def test_orc_03_job_search_routes_with_filters(harness: GraphHarness):
    """TC-ORC-03: 'Tìm việc Python Backend Intern tại TP.HCM' -> Job Search."""
    harness.analyzer.on("tìm việc", intent(I.JOB_SEARCH, patch=SEARCH_PATCH))

    response = await harness.send("Tìm việc Python Backend Intern tại TP.HCM.")

    assert response.route == ConversationRoute.JOB_SEARCH
    assert response.status == ConversationStatus.COMPLETED
    assert response.workflow.workflow_type == WorkflowType.JOB_DISCOVERY
    assert response.job_search_result is not None
    request, _ = harness.job_search.requests[0]
    assert request.filters.locations == ["Hồ Chí Minh"]
    assert [s.value for s in request.filters.seniority_levels] == ["intern"]
    assert "Current user request" in request.query  # contextual message used
    assert response.search_context.location == "Hồ Chí Minh"


async def test_orc_04_search_context_persists_across_turns(harness: GraphHarness):
    """TC-ORC-04: saved constraints are reused and merged on the next turn."""
    harness.analyzer.on("tìm việc", intent(I.JOB_SEARCH, patch=SEARCH_PATCH))
    harness.analyzer.on("remote", intent(I.JOB_SEARCH, patch={"work_mode": "remote"}))

    await harness.send("Tìm việc Python Backend Intern tại TP.HCM.")
    second = await harness.send("Chỉ lấy việc remote thôi")

    request, _ = harness.job_search.requests[-1]
    assert request.filters.locations == ["Hồ Chí Minh"]
    assert [m.value for m in request.filters.work_modes] == ["remote"]
    assert second.search_context.seniority.value == "intern"


async def test_orc_04b_clear_fields_removes_constraint(harness: GraphHarness):
    """TC-ORC-04b: clear_fields in the patch removes a saved constraint."""
    harness.analyzer.on("tìm việc", intent(I.JOB_SEARCH, patch=SEARCH_PATCH))
    harness.analyzer.on("bỏ địa điểm", intent(I.JOB_SEARCH, patch={"clear_fields": ["location"]}))

    await harness.send("Tìm việc Python Backend Intern tại TP.HCM.")
    await harness.send("Bỏ địa điểm đi")

    request, _ = harness.job_search.requests[-1]
    assert request.filters.locations == []


# --------------------------------------------------------------------------
# Scenario 3 – Matching with "the job just found"
# --------------------------------------------------------------------------
async def test_orc_06_matching_with_explicit_jd(harness: GraphHarness):
    """TC-ORC-06: UI path – CV + explicit job_description -> Job Matching."""
    harness.analyzer.on("so khớp", intent(I.JOB_MATCHING))
    cv_id = harness.add_cv()

    response = await harness.send("So khớp CV với JD này", cv_id=cv_id, job_description=JD)

    assert response.route == ConversationRoute.JOB_MATCHING
    assert response.status == ConversationStatus.COMPLETED
    assert harness.job_matching.inputs[0].job.description.startswith("Backend Intern")


async def test_orc_05_match_with_job_just_found_uses_previous_search(harness: GraphHarness):
    """TC-ORC-05 (Scenario 3, BUG-005 fixed): 'So khớp CV của tôi với công
    việc vừa tìm' re-uses the CV and the jobs found on the previous turn."""
    harness.analyzer.on("tìm việc", intent(I.JOB_SEARCH, patch=SEARCH_PATCH))
    harness.analyzer.on("so khớp", intent(I.JOB_MATCHING))
    cv_id = harness.add_cv()

    first = await harness.send("Tìm việc Python Backend Intern tại TP.HCM.", cv_id=cv_id)
    response = await harness.send("So khớp CV của tôi với công việc vừa tìm.")

    assert response.status == ConversationStatus.COMPLETED
    assert response.route == ConversationRoute.JOB_MATCHING
    found_ids = [hit.job.job_id for hit in first.job_search_result.items]
    assert sorted(i.job.job_id for i in harness.job_matching.inputs) == sorted(found_ids)
    assert all(i.cv_profile is not None for i in harness.job_matching.inputs)
    assert len(response.workflow_job_matches) == len(found_ids)
    assert response.job_matching_result is not None
    assert response.matching_execution.status == WorkflowExecutionStatus.SUCCESS
    assert "công việc vừa tìm" in response.assistant_message


async def test_orc_05b_per_turn_results_reset_but_focus_kept(harness: GraphHarness):
    """TC-ORC-05b: per-turn results are still reset in prepare_turn (no stale
    answer leaks into the next turn) while the remembered jobs survive."""
    harness.analyzer.on("tìm việc", intent(I.JOB_SEARCH, patch=SEARCH_PATCH))
    harness.analyzer.on("xin chào", intent(I.SMALL_TALK))
    cv_id = harness.add_cv()

    await harness.send("Tìm việc Python Backend Intern tại TP.HCM.", cv_id=cv_id)
    response = await harness.send("Xin chào")

    assert response.job_search_result is None
    state = await harness.state()
    assert state["job_search_result"] is None
    assert len(state["recent_jobs"]) == 3


async def test_orc_05c_without_any_job_still_asks_for_jd(harness: GraphHarness):
    """TC-ORC-05c: no previous search and no JD -> clarification as before."""
    harness.analyzer.on("so khớp", intent(I.JOB_MATCHING))
    response = await harness.send("So khớp CV của tôi với công việc vừa tìm.",
                                  cv_id=harness.add_cv())
    assert response.status == ConversationStatus.NEEDS_CLARIFICATION
    assert response.missing_inputs == [RequiredInput.JOB_DESCRIPTION]
    assert harness.job_matching.inputs == []


async def test_orc_05d_empty_search_clears_remembered_jobs(harness: GraphHarness):
    """TC-ORC-05d: if the latest search found nothing, 'the job just found'
    no longer refers to an older result set."""
    harness.analyzer.on("tìm việc", intent(I.JOB_SEARCH, patch=SEARCH_PATCH))
    harness.analyzer.on("so khớp", intent(I.JOB_MATCHING))
    cv_id = harness.add_cv()

    await harness.send("Tìm việc Python Backend Intern tại TP.HCM.", cv_id=cv_id)
    harness.job_search.jobs = []
    await harness.send("Tìm việc Rust tại Hà Nội")
    response = await harness.send("So khớp CV của tôi với công việc vừa tìm.")

    assert response.status == ConversationStatus.NEEDS_CLARIFICATION
    assert harness.job_matching.inputs == []


async def test_orc_05e_fresh_jd_wins_over_remembered_jobs(harness: GraphHarness):
    """TC-ORC-05e: a JD pasted in this request is matched instead of the
    remembered search results; an older JD does not override newer jobs."""
    harness.analyzer.on("tìm việc", intent(I.JOB_SEARCH, patch=SEARCH_PATCH))
    harness.analyzer.on("so khớp", intent(I.JOB_MATCHING))
    cv_id = harness.add_cv()

    await harness.send("Tìm việc Python Backend Intern tại TP.HCM.", cv_id=cv_id)
    direct = await harness.send("So khớp CV với JD này", job_description=JD)
    assert [i.job.description for i in harness.job_matching.inputs] == [JD]
    assert direct.workflow_job_matches == []

    harness.job_matching.inputs.clear()
    await harness.send("Tìm việc Python Backend Intern tại TP.HCM.")
    await harness.send("So khớp CV của tôi với công việc vừa tìm.")
    assert len(harness.job_matching.inputs) == 3
    assert all(i.job.job_id for i in harness.job_matching.inputs)


# --------------------------------------------------------------------------
# Scenario 4 – Career advice grounded on the previous match
# --------------------------------------------------------------------------
async def test_orc_07_career_advice_uses_previous_matching_result(harness: GraphHarness):
    """TC-ORC-07 (Scenario 4, BUG-006 fixed): 'Tôi cần học thêm gì để phù hợp
    công việc này?' is grounded on the gaps of the previous match."""
    harness.analyzer.on("so khớp", intent(I.JOB_MATCHING))
    harness.analyzer.on("học thêm", intent(I.CAREER_ADVICE))
    cv_id = harness.add_cv()

    matched = await harness.send("So khớp CV với JD này", cv_id=cv_id, job_description=JD)
    await harness.send("Tôi cần học thêm gì để phù hợp công việc này?")

    advice_input = harness.career_advice.inputs[-1]
    assert [r.summary for r in advice_input.matching_results] == [
        matched.job_matching_result.summary]
    assert advice_input.matching_results[0].gaps == ["Kubernetes"]


async def test_orc_07c_previous_match_of_another_cv_is_not_used(harness: GraphHarness):
    """TC-ORC-07c: switching to another CV invalidates the remembered match
    (its gaps belong to a different candidate)."""
    harness.analyzer.on("so khớp", intent(I.JOB_MATCHING))
    harness.analyzer.on("học thêm", intent(I.CAREER_ADVICE))

    await harness.send("So khớp CV với JD này", cv_id=harness.add_cv(), job_description=JD)
    await harness.send("Tôi cần học thêm gì?", cv_id=harness.add_cv())

    assert harness.career_advice.inputs[-1].matching_results == []


async def test_orc_07b_career_advice_keeps_cv(harness: GraphHarness):
    """TC-ORC-07b: the CV selected earlier is still used (cv_id kept in state)."""
    harness.analyzer.on("so khớp", intent(I.JOB_MATCHING))
    harness.analyzer.on("học thêm", intent(I.CAREER_ADVICE))
    cv_id = harness.add_cv()

    await harness.send("So khớp CV với JD này", cv_id=cv_id, job_description=JD)
    response = await harness.send("Tôi cần học thêm gì để phù hợp công việc này?")

    assert response.route == ConversationRoute.CAREER_ADVICE
    assert harness.career_advice.inputs[-1].cv_profile is not None
    assert response.career_advice_result.is_personalized is True


# --------------------------------------------------------------------------
# Scenario 5 – Cover letter with human-in-the-loop
# --------------------------------------------------------------------------
async def _start_cover_letter(harness: GraphHarness):
    harness.analyzer.on("cover letter", intent(I.COVER_LETTER))
    cv_id = harness.add_cv()
    response = await harness.send("Viết Cover Letter cho công việc đó.", cv_id=cv_id,
                                  job_description=JD)
    return cv_id, response


async def test_orc_08_cover_letter_full_hitl_flow(harness: GraphHarness):
    """TC-ORC-08: confirm input -> draft -> approve draft -> completed."""
    cv_id, first = await _start_cover_letter(harness)
    assert first.status == ConversationStatus.WAITING_FOR_HUMAN
    assert first.human_review.review_type == "cover_letter_confirmation"
    assert harness.cover_letter.inputs == []  # nothing generated before approval

    second = await harness.resume(first.human_review.review_id)
    assert second.status == ConversationStatus.WAITING_FOR_HUMAN
    assert second.human_review.review_type == "cover_letter_draft"
    letter_input = harness.cover_letter.inputs[0]
    assert letter_input.job.description.startswith("Backend Intern")
    assert letter_input.cv_profile == harness.cv_repository.profiles[cv_id]

    third = await harness.resume(second.human_review.review_id)
    assert third.status == ConversationStatus.COMPLETED
    assert third.route == ConversationRoute.COVER_LETTER
    assert third.cover_letter_result is not None


async def test_orc_09_cover_letter_rejected_at_confirmation(harness: GraphHarness):
    """TC-ORC-09: reject at confirmation -> stop, no LLM generation."""
    _, first = await _start_cover_letter(harness)
    response = await harness.resume(first.human_review.review_id, "reject", feedback="Đổi JD")

    assert response.status == ConversationStatus.COMPLETED
    assert "Đã dừng" in response.assistant_message
    assert "Đổi JD" in response.assistant_message
    assert harness.cover_letter.inputs == []


async def test_orc_10_stale_review_id_is_rejected(harness: GraphHarness):
    """TC-ORC-10: a review_id that does not match the pending review -> 409."""
    _, _ = await _start_cover_letter(harness)
    with pytest.raises(AppException) as error:
        await harness.resume("review_" + "0" * 16)
    assert error.value.status_code == 409
    assert error.value.code == "STALE_HUMAN_REVIEW"


async def test_orc_11_new_message_while_review_pending(harness: GraphHarness):
    """TC-ORC-11: sending a message while waiting for review -> 409."""
    await _start_cover_letter(harness)
    with pytest.raises(AppException) as error:
        await harness.send("Xin chào")
    assert error.value.code == "HUMAN_REVIEW_PENDING"


async def test_orc_12_resume_without_pending_review(harness: GraphHarness):
    """TC-ORC-12: resume when nothing is pending -> 409; unknown thread -> 404."""
    harness.analyzer.on("xin chào", intent(I.SMALL_TALK))
    await harness.send("Xin chào")
    with pytest.raises(AppException) as error:
        await harness.resume("review_" + "a" * 16)
    assert error.value.code == "HUMAN_REVIEW_NOT_PENDING"

    other = GraphHarness()
    with pytest.raises(ResourceNotFoundException):
        await other.resume("review_" + "a" * 16)


async def test_orc_13_edited_draft_is_applied(harness: GraphHarness):
    """TC-ORC-13: approve with edited_draft -> the user's text is returned."""
    _, first = await _start_cover_letter(harness)
    second = await harness.resume(first.human_review.review_id)
    final = await harness.resume(second.human_review.review_id,
                                 edited_draft="Bản chỉnh sửa của tôi gồm năm từ")
    assert final.cover_letter_result.full_text == "Bản chỉnh sửa của tôi gồm năm từ"
    assert final.cover_letter_result.word_count == 8


async def test_orc_13b_override_selection_outside_review_is_rejected(harness: GraphHarness):
    """TC-ORC-13b: selected_job_id not in the review candidates -> 409."""
    _, first = await _start_cover_letter(harness)
    with pytest.raises(AppException) as error:
        await harness.resume(first.human_review.review_id, selected_job_id="evil")
    assert error.value.code == "INVALID_REVIEW_SELECTION"


# --------------------------------------------------------------------------
# Multi-agent workflows
# --------------------------------------------------------------------------
async def test_orc_14_search_then_match_ranks_top_jobs(harness: GraphHarness):
    """TC-ORC-14: JOB_RECOMMENDATION matches at most 5 jobs, ranked by score."""
    jobs = [make_job(i, title=f"Job {i}") for i in range(7)]
    harness.job_search.jobs = jobs
    for index, job in enumerate(jobs):
        harness.job_matching.scores[job.job_id] = 50 + index * 5
    harness.analyzer.on("phù hợp", intent(I.JOB_SEARCH, I.JOB_MATCHING))
    cv_id = harness.add_cv()

    response = await harness.send("Tìm việc phù hợp với CV", cv_id=cv_id)

    assert response.workflow.workflow_type == WorkflowType.JOB_RECOMMENDATION
    assert len(harness.job_matching.inputs) == 5
    scores = [item.match.overall_score for item in response.workflow_job_matches]
    assert scores == sorted(scores, reverse=True)
    assert response.matching_execution.status == WorkflowExecutionStatus.SUCCESS
    assert response.status == ConversationStatus.COMPLETED


async def test_orc_15_partial_matching_failure(harness: GraphHarness):
    """TC-ORC-15: one job fails to match -> PARTIAL_SUCCESS, others kept."""
    jobs = [make_job(i) for i in range(3)]
    harness.job_search.jobs = jobs
    harness.job_matching.failures.add(jobs[1].job_id)
    harness.analyzer.on("phù hợp", intent(I.JOB_SEARCH, I.JOB_MATCHING))

    response = await harness.send("Tìm việc phù hợp", cv_id=harness.add_cv())

    execution = response.matching_execution
    assert (execution.succeeded, execution.failed, execution.total) == (2, 1, 3)
    assert response.status == ConversationStatus.PARTIAL_SUCCESS
    failed = [o for o in response.workflow_job_match_outcomes if o.status.value == "failed"]
    assert failed[0].error_code == "INVALID_STRUCTURED_OUTPUT"


async def test_orc_16_matching_timeout_marks_jobs_skipped():
    """TC-ORC-16: workflow timeout -> slow jobs SKIPPED, no hang."""
    harness = GraphHarness(workflow_timeout=0.2)
    jobs = [make_job(i) for i in range(2)]
    harness.job_search.jobs = jobs
    harness.job_matching.delay_for[jobs[0].job_id] = 5
    harness.analyzer.on("phù hợp", intent(I.JOB_SEARCH, I.JOB_MATCHING))

    response = await asyncio.wait_for(
        harness.send("Tìm việc phù hợp", cv_id=harness.add_cv()), timeout=3
    )

    assert response.matching_execution.skipped == 1
    assert response.status == ConversationStatus.PARTIAL_SUCCESS


async def test_orc_17_search_plus_cover_letter_with_no_results(harness: GraphHarness):
    """TC-ORC-17 (BUG-007 fixed): search+cover letter, search returns 0 jobs ->
    clarification asking for a JD; no crash, no review, no generation."""
    harness.job_search.jobs = []
    harness.analyzer.on("viết", intent(I.JOB_SEARCH, I.COVER_LETTER))

    response = await harness.send("Tìm việc Python và viết cover letter",
                                  cv_id=harness.add_cv())
    assert response.status == ConversationStatus.NEEDS_CLARIFICATION
    assert response.missing_inputs == [RequiredInput.JOB_DESCRIPTION]
    assert response.human_review is None
    assert "JD" in response.assistant_message
    assert harness.cover_letter.inputs == []

    # The thread is not stuck: the next turn works normally.
    harness.analyzer.on("xin chào", intent(I.SMALL_TALK))
    follow_up = await harness.send("Xin chào")
    assert follow_up.status == ConversationStatus.COMPLETED


async def test_orc_17b_cover_letter_for_job_just_found(harness: GraphHarness):
    """TC-ORC-17b (Scenario 5): 'Viết Cover Letter cho công việc đó' after a
    search offers the remembered jobs at the human review."""
    harness.analyzer.on("tìm việc", intent(I.JOB_SEARCH, patch=SEARCH_PATCH))
    harness.analyzer.on("cover letter", intent(I.COVER_LETTER))
    cv_id = harness.add_cv()

    first = await harness.send("Tìm việc Python Backend Intern tại TP.HCM.", cv_id=cv_id)
    review = await harness.send("Viết Cover Letter cho công việc đó.")

    assert review.status == ConversationStatus.WAITING_FOR_HUMAN
    offered = [job["job_id"] for job in review.human_review.data["jobs"]]
    assert offered == [hit.job.job_id for hit in first.job_search_result.items]
    draft = await harness.resume(review.human_review.review_id)
    assert harness.cover_letter.inputs[0].job.job_id == offered[0]
    final = await harness.resume(draft.human_review.review_id)
    assert final.status == ConversationStatus.COMPLETED


async def test_orc_18_cv_analysis_plus_matching_reply_contains_match(harness: GraphHarness):
    """TC-ORC-18 (BUG-008 fixed): [CV_ANALYSIS, JOB_MATCHING] with a JD -> reply
    contains both the CV score and the match score."""
    harness.analyzer.on("đánh giá", intent(I.CV_ANALYSIS, I.JOB_MATCHING))

    response = await harness.send("Đánh giá CV và so khớp với JD", cv_id=harness.add_cv(),
                                  job_description=JD)

    assert response.job_matching_result is not None
    assert "Điểm chất lượng nội dung CV" in response.assistant_message
    assert "Mức độ phù hợp của CV với công việc là 72.00/100" in response.assistant_message


async def test_orc_26_no_jobs_found_is_not_a_failure(harness: GraphHarness):
    """TC-ORC-26 (BUG-017 fixed): search+match with zero jobs -> completed with
    a 'no results' execution summary and advice to widen the criteria."""
    harness.job_search.jobs = []
    harness.analyzer.on("phù hợp", intent(I.JOB_SEARCH, I.JOB_MATCHING))

    response = await harness.send("Tìm việc phù hợp", cv_id=harness.add_cv())
    assert response.status == ConversationStatus.COMPLETED
    assert response.matching_execution.status == WorkflowExecutionStatus.NO_RESULTS
    assert response.matching_execution.total == 0
    assert "mở rộng" in response.assistant_message
    assert harness.job_matching.inputs == []


async def test_orc_26b_all_matches_failing_is_still_a_failure(harness: GraphHarness):
    """TC-ORC-26b: a real failure (every job errors) is still reported FAILED."""
    jobs = [make_job(i) for i in range(2)]
    harness.job_search.jobs = jobs
    harness.job_matching.failures.update(job.job_id for job in jobs)
    harness.analyzer.on("phù hợp", intent(I.JOB_SEARCH, I.JOB_MATCHING))

    response = await harness.send("Tìm việc phù hợp", cv_id=harness.add_cv())
    assert response.status == ConversationStatus.FAILED
    assert response.matching_execution.status == WorkflowExecutionStatus.FAILED


# --------------------------------------------------------------------------
# State, memory, routing and robustness
# --------------------------------------------------------------------------
async def test_orc_20_cv_id_persists_and_profile_not_retained(harness: GraphHarness):
    """TC-ORC-20: cv_id is remembered; the full CV is not kept in the checkpoint."""
    harness.analyzer.on("phân tích", intent(I.CV_ANALYSIS))
    cv_id = harness.add_cv()

    await harness.send("Phân tích CV", cv_id=cv_id)
    second = await harness.send("Phân tích CV lần nữa")  # cv_id not resent

    assert second.cv_id == cv_id
    assert second.route == ConversationRoute.CV_ANALYSIS
    assert (await harness.state()).get("cv_profile") is None


async def test_orc_20b_cv_can_be_detached(harness: GraphHarness):
    """TC-ORC-20b: sending cv_id=None explicitly detaches the CV."""
    harness.analyzer.on("phân tích", intent(I.CV_ANALYSIS))
    cv_id = harness.add_cv()
    await harness.send("Phân tích CV", cv_id=cv_id)
    response = await harness.send("Phân tích CV", cv_id=None)
    assert response.missing_inputs == [RequiredInput.CV]


BUSINESS_INTENTS = [I.CV_ANALYSIS, I.JOB_SEARCH, I.JOB_MATCHING, I.CAREER_ADVICE,
                    I.COVER_LETTER]


@pytest.mark.parametrize("mask", range(1, 32))
async def test_orc_21_every_intent_combination_terminates(mask: int):
    """TC-ORC-21: all 31 intent combinations finish (or pause for HITL) without
    hitting LangGraph's recursion limit, i.e. no infinite agent loop."""
    from langgraph.errors import GraphRecursionError

    selected = [value for bit, value in enumerate(BUSINESS_INTENTS) if mask >> bit & 1]
    harness = GraphHarness()
    harness.analyzer.on("go", intent(selected[0], *selected[1:]))
    try:
        response = await asyncio.wait_for(
            harness.send("go", cv_id=harness.add_cv(), job_description=JD), timeout=5
        )
    except GraphRecursionError:  # pragma: no cover - would be a real defect
        pytest.fail(f"infinite loop for {selected}")
    while response.status == ConversationStatus.WAITING_FOR_HUMAN:
        response = await harness.resume(response.human_review.review_id)
    assert response.status in {ConversationStatus.COMPLETED,
                               ConversationStatus.PARTIAL_SUCCESS}


def test_orc_21b_step_outside_plan_terminates_workflow():
    """TC-ORC-21b (BUG-030 fixed): a step missing from the plan now completes
    the workflow instead of leaving current_step unchanged, and the router
    never re-enters a step that already ran, so the self-edges of workflow
    nodes cannot spin until the recursion limit."""
    from app.graphs.conversation.routing import WorkflowRoute, route_next_workflow_step
    from app.graphs.conversation.workflow import advance_workflow
    from app.schemas.workflow import WorkflowPlan, WorkflowStep

    plan = WorkflowPlan(workflow_type=WorkflowType.FULL_CAREER,
                        steps=[WorkflowStep.CV_ANALYSIS],
                        current_step=WorkflowStep.JOB_MATCHING)
    advanced = advance_workflow(plan, WorkflowStep.JOB_MATCHING)
    assert advanced.current_step == WorkflowStep.COMPLETED
    assert route_next_workflow_step({"workflow": advanced}) == WorkflowRoute.END

    stuck = plan.model_copy(update={"completed_steps": [WorkflowStep.JOB_MATCHING]})
    assert route_next_workflow_step({"workflow": stuck}) == WorkflowRoute.END


def test_orc_21c_dead_single_agent_search_node_removed():
    """TC-ORC-21c (BUG-030): the unreachable single-agent 'job_search' node is
    gone; job search always runs as the workflow node."""
    nodes = set(GraphHarness().graph.get_graph().nodes)
    assert "job_search" not in nodes
    assert "workflow_job_search" in nodes


def test_orc_21d_workflow_error_messages_name_the_right_step():
    """TC-ORC-21d (BUG-030): invariant errors name the node that raised them."""
    import inspect

    from app.graphs.conversation.nodes import ConversationNodes

    matching = inspect.getsource(ConversationNodes.execute_workflow_job_matching)
    analysis = inspect.getsource(ConversationNodes.execute_workflow_cv_analysis)
    assert "for workflow CV analysis" not in matching
    assert "for workflow job matching" not in analysis


async def test_orc_22_intent_analysis_has_no_side_effects(harness: GraphHarness):
    """TC-ORC-22 (BUG-009 fixed): the diagnostic intent-analysis call must not
    alter history nor leave the CV profile in a checkpoint."""
    from app.schemas.conversations_intent import ConversationRequest

    harness.analyzer.on("phân tích", intent(I.CV_ANALYSIS))
    cv_id = harness.add_cv()
    result = await harness.service.analyze_intent(
        ConversationRequest(thread_id=harness.thread_id, message="Phân tích CV", cv_id=cv_id)
    )
    assert result.primary_intent == I.CV_ANALYSIS
    assert harness.analyzer.calls[-1].has_cv is True  # CV was really resolved
    state = await harness.state()
    assert state.get("messages", []) == []
    assert state.get("cv_profile") is None
    assert harness.cv_analysis.inputs == []  # stopped after intent analysis
    # Nothing is left behind in the private diagnostic checkpointer either.
    saver = harness.service._diagnostic_saver
    assert saver is not None and not saver.storage


async def test_orc_22b_intent_analysis_sees_existing_history(harness: GraphHarness):
    """TC-ORC-22b: the diagnostic call reads (but never writes) the existing
    thread history and search context."""
    from app.schemas.conversations_intent import ConversationRequest

    harness.analyzer.on("tìm việc", intent(I.JOB_SEARCH, patch=SEARCH_PATCH))
    await harness.send("Tìm việc Python Backend Intern tại TP.HCM.")
    before = await harness.state()

    await harness.service.analyze_intent(
        ConversationRequest(thread_id=harness.thread_id, message="Tìm việc remote"))

    seen = harness.analyzer.calls[-1]
    assert "Tìm việc Python Backend Intern" in seen.conversation_history
    assert seen.search_context.location == "Hồ Chí Minh"
    after = await harness.state()
    assert len(after["messages"]) == len(before["messages"])


async def test_orc_23_clarification_intent(harness: GraphHarness):
    """TC-ORC-23: ambiguous request -> generated clarification question."""
    harness.analyzer.on("giúp", intent(I.CLARIFICATION, clarification="Bạn cần hỗ trợ gì?"))
    response = await harness.send("Giúp tôi với")
    assert response.route == ConversationRoute.CLARIFICATION
    assert response.assistant_message == "Bạn cần hỗ trợ gì?"


@pytest.mark.parametrize(
    ("message", "value", "route"),
    [
        ("xin chào", I.SMALL_TALK, ConversationRoute.SMALL_TALK),
        ("thời tiết", I.OUT_OF_SCOPE, ConversationRoute.OUT_OF_SCOPE),
    ],
)
async def test_orc_24_non_business_routes(harness: GraphHarness, message, value, route):
    """TC-ORC-24: small talk / out-of-scope do not call any business agent."""
    harness.analyzer.on(message, intent(value))
    response = await harness.send(message)
    assert response.route == route
    assert not harness.cv_analysis.inputs and not harness.job_search.requests


async def test_orc_25_agent_error_does_not_poison_thread(harness: GraphHarness):
    """TC-ORC-25: an agent failure surfaces as AppException; next turn still works."""
    harness.analyzer.on("phân tích", intent(I.CV_ANALYSIS))
    harness.analyzer.on("xin chào", intent(I.SMALL_TALK))
    cv_id = harness.add_cv()

    async def broken(_):
        raise AppException(status_code=502, code="EXTERNAL_SERVICE_ERROR", message="down")

    original = harness.cv_analysis.analyze
    harness.cv_analysis.analyze = broken
    with pytest.raises(AppException):
        await harness.send("Phân tích CV", cv_id=cv_id)
    harness.cv_analysis.analyze = original

    response = await harness.send("Xin chào")
    assert response.status == ConversationStatus.COMPLETED


async def test_orc_27_history_endpoint_returns_turns(harness: GraphHarness):
    """TC-ORC-27: conversation history contains user + assistant messages in order."""
    harness.analyzer.on("xin chào", intent(I.SMALL_TALK))
    await harness.send("Xin chào")
    history = await harness.service.get_history(harness.thread_id)
    assert [m.role for m in history.messages] == ["user", "assistant"]
    assert history.latest_result["route"] == "small_talk"
