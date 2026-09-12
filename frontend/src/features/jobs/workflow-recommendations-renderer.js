import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import { clampMatchingScore } from "../../shared/formatters.js";
import { escapeHtml } from "../../shared/html.js";
import { getRecommendationLabel } from "../../shared/labels.js";

export function createWorkflowRecommendationsRenderer({
  openResultsPanel,
  showNoJobResults,
  updateMobileResultsBadge,
}) {
  function renderWorkflowJobRecommendations(
    searchResult,
    matches,
    careerAdvice,
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
      "Công việc phù hợp nhất";
    elements.resultsSummary.hidden = false;
    elements.jobSort.disabled = true;
    elements.backToJobsButton.hidden = true;
    elements.resultCount.textContent =
      `${normalizedMatches.length} công việc phù hợp nhất với CV`;
    elements.searchStrategy.textContent =
      "Multi-Agent Matching";

    updateMobileResultsBadge(normalizedMatches.length);
    openResultsPanel();

    if (!normalizedMatches.length) {
      showNoJobResults();
      return;
    }

    elements.jobResults.innerHTML = `
      <section
        class="workflow-recommendations"
        aria-label="Danh sách công việc phù hợp"
      >
        ${normalizedMatches
          .map(renderWorkflowJobCard)
          .join("")}
        ${
          careerAdvice
            ? renderWorkflowCareerSummary(careerAdvice)
            : ""
        }
      </section>
    `;
  }

  return { renderWorkflowJobRecommendations };
}

function renderWorkflowJobCard(item, index) {
  const job = item?.job ?? {};
  const match = item?.match ?? {};
  const score = clampMatchingScore(match.overallScore);
  const strengths = toArray(match.strengths).slice(0, 3);
  const gaps = toArray(match.gaps).slice(0, 3);

  return `
    <article class="workflow-job-card">
      <header class="workflow-job-header">
        <div class="workflow-job-rank">#${index + 1}</div>
        <div class="workflow-job-title">
          <h3>${escapeHtml(job.title || "Vị trí chưa xác định")}</h3>
          <p>
            ${escapeHtml(job.company || "Chưa rõ công ty")}
            ·
            ${escapeHtml(job.location || "Chưa rõ địa điểm")}
          </p>
        </div>
        <div class="workflow-match-score">
          <strong>${score.toFixed(1)}</strong>
          <span>/100</span>
        </div>
      </header>

      <div class="workflow-match-meta">
        <span class="recommendation-badge">
          ${escapeHtml(getRecommendationLabel(match.recommendation))}
        </span>
      </div>

      <div class="workflow-match-columns">
        <section>
          <h4>Điểm mạnh</h4>
          ${renderList(strengths, "Chưa có dữ liệu.")}
        </section>
        <section>
          <h4>Khoảng trống</h4>
          ${renderList(gaps, "Chưa có khoảng trống đáng kể.")}
        </section>
      </div>

      <div class="workflow-job-actions">
        <button
          type="button"
          class="secondary-button"
          data-action="view-job"
          data-job-id="${escapeHtml(job.job_id ?? "")}"
        >
          Xem công việc
        </button>
        <button
          type="button"
          class="primary-button"
          data-action="cover-letter-job"
          data-job-id="${escapeHtml(job.job_id ?? "")}"
        >
          Viết Cover Letter
        </button>
      </div>
    </article>
  `;
}

function renderWorkflowCareerSummary(advice) {
  const skills = toArray(advice.topPrioritySkills);

  return `
    <section class="workflow-career-summary">
      <span class="career-personalization-badge personalized">
        Career Advisor
      </span>
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

function renderList(items, emptyMessage) {
  if (!items.length) {
    return `<p>${escapeHtml(emptyMessage)}</p>`;
  }

  return `
    <ul>
      ${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
    </ul>
  `;
}

function toArray(value) {
  return Array.isArray(value) ? value : [];
}
