import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import { clampMatchingScore } from "../../shared/formatters.js";
import { escapeHtml } from "../../shared/html.js";
import { icon } from "../../shared/icons.js";
import {
  getExecutionStatusLabel,
  getRecommendationLabel,
} from "../../shared/labels.js";
import { getRecommendationTone, getScoreTone } from "../matching/score-tones.js";

export function createWorkflowRecommendationsRenderer({
  openResultsPanel,
  showNoJobResults,
  updateMobileResultsBadge,
}) {
  function renderWorkflowJobRecommendations(
    searchResult,
    matches,
    careerAdvice,
    { matchingExecution = null, outcomes = [] } = {},
  ) {
    const normalizedMatches = Array.isArray(matches)
      ? matches
      : [];

    state.currentSearchResult = searchResult;
    state.workflowJobMatches = normalizedMatches;
    state.jobs = normalizedMatches.map((item) => ({
      job: item.job,
      workflowMatch: item.match,
    }));

    elements.resultsEyebrow.textContent =
      "AI JOB RECOMMENDATION";
    elements.resultsTitle.textContent =
      "Công việc phù hợp nhất với CV";
    elements.resultsSummary.hidden = true;
    elements.jobSort.disabled = true;
    elements.backToJobsButton.hidden = true;
    elements.activeFilters.innerHTML = "";
    if (elements.jobPagination) elements.jobPagination.hidden = true;

    updateMobileResultsBadge(normalizedMatches.length);
    openResultsPanel();

    if (!normalizedMatches.length) {
      showNoJobResults();
      return;
    }

    const unmatched = (Array.isArray(outcomes) ? outcomes : []).filter(
      (outcome) => outcome?.status && outcome.status !== "success",
    );

    elements.jobResults.innerHTML = `
      <section
        class="workflow-recommendations"
        aria-label="Danh sách công việc phù hợp"
      >
        ${renderExecutionSummary(normalizedMatches.length, matchingExecution)}
        ${normalizedMatches
          .map(renderWorkflowJobCard)
          .join("")}
        ${renderUnmatched(unmatched)}
        ${
          careerAdvice
            ? renderWorkflowCareerSummary(careerAdvice)
            : ""
        }
      </section>
    `;
    elements.jobResults.scrollTop = 0;
  }

  return { renderWorkflowJobRecommendations };
}

function renderExecutionSummary(count, execution) {
  const total = Number(execution?.total);

  return `
    <div class="execution-summary">
      <span>
        <strong>${count}</strong> công việc được xếp hạng theo mức độ phù hợp với CV
      </span>
      ${
        execution && Number.isFinite(total) && total > 0
          ? `<span class="muted">
              Job Matching Agent · ${Number(execution.succeeded)}/${total} lượt so khớp ·
              ${escapeHtml(getExecutionStatusLabel(execution.status))}
            </span>`
          : ""
      }
    </div>
  `;
}

function renderWorkflowJobCard(item, index) {
  const job = item?.job ?? {};
  const match = item?.match ?? {};
  const score = clampMatchingScore(match.overallScore);
  const strengths = toArray(match.strengths).slice(0, 3);
  const gaps = toArray(match.gaps).slice(0, 3);
  const jobId = escapeHtml(job.job_id ?? "");

  return `
    <article class="workflow-job-card" style="animation-delay: ${Math.min(index, 6) * 40}ms">
      <header class="workflow-job-header">
        <div class="workflow-job-rank" aria-label="Hạng ${index + 1}">${index + 1}</div>
        <div class="workflow-job-title">
          <h3>${escapeHtml(job.title || "Vị trí chưa xác định")}</h3>
          <p>
            ${escapeHtml(
              [job.company || "Chưa rõ công ty", job.location].filter(Boolean).join(" · "),
            )}
          </p>
        </div>
        <div class="workflow-match-score" aria-label="Điểm phù hợp ${score.toFixed(1)} trên 100">
          <strong>${score.toFixed(1)}</strong>
          <span>/100</span>
        </div>
      </header>

      <div class="score-meter ${getScoreTone(score)}" aria-hidden="true">
        <span style="--value: ${score}"></span>
      </div>

      <div>
        <span class="badge ${getRecommendationTone(match.recommendation)}">
          ${escapeHtml(getRecommendationLabel(match.recommendation))}
        </span>
      </div>

      <div class="workflow-match-columns">
        <section class="insight-section">
          <h3>Điểm mạnh</h3>
          ${renderFindings(strengths, "is-strength", "Chưa có dữ liệu.")}
        </section>
        <section class="insight-section">
          <h3>Khoảng trống</h3>
          ${renderFindings(gaps, "is-gap", "Chưa ghi nhận khoảng trống đáng kể.")}
        </section>
      </div>

      <footer class="workflow-job-actions">
        <button
          type="button"
          class="btn btn-ghost btn-sm"
          data-action="view-job"
          data-job-id="${jobId}"
        >
          Xem công việc
        </button>
        <button
          type="button"
          class="btn btn-primary btn-sm"
          data-action="cover-letter-job"
          data-job-id="${jobId}"
        >
          ${icon("mail")} Viết thư ứng tuyển
        </button>
      </footer>
    </article>
  `;
}

function renderUnmatched(outcomes) {
  if (!outcomes.length) {
    return "";
  }

  const statusLabels = {
    failed: "Lỗi khi so khớp",
    skipped: "Bỏ qua",
  };

  return `
    <section class="workflow-skipped insight-section">
      <h3>Chưa so khớp được (${outcomes.length})</h3>
      <ul>
        ${outcomes
          .map(
            (outcome) => `
              <li>
                <span>${escapeHtml(outcome.job?.title || "Công việc")}</span>
                <span class="muted">${escapeHtml(statusLabels[outcome.status] ?? outcome.status)}</span>
              </li>
            `,
          )
          .join("")}
      </ul>
    </section>
  `;
}

function renderWorkflowCareerSummary(advice) {
  const skills = toArray(advice.topPrioritySkills);

  return `
    <section class="workflow-career-summary">
      <p class="eyebrow">Career Advice Agent</p>
      <h3>Bạn nên cải thiện gì tiếp theo?</h3>
      <p>${escapeHtml(advice.summary || "Chưa có nhận xét.")}</p>
      ${
        skills.length
          ? `<div class="career-skill-chips">
              ${skills
                .map((skill) => `<span>${escapeHtml(skill)}</span>`)
                .join("")}
            </div>`
          : ""
      }
    </section>
  `;
}

function renderFindings(items, variant, emptyMessage) {
  if (!items.length) {
    return `<p class="insight-empty">${escapeHtml(emptyMessage)}</p>`;
  }

  const marker = variant === "is-strength" ? icon("check") : icon("minus");

  return `
    <ul class="finding-list ${variant}">
      ${items
        .map(
          (item) => `
            <li>
              <span class="finding-marker">${marker}</span>
              <span>${escapeHtml(item)}</span>
            </li>
          `,
        )
        .join("")}
    </ul>
  `;
}

function toArray(value) {
  return Array.isArray(value) ? value : [];
}
