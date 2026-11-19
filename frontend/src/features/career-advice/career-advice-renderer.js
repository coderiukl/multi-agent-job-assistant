import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import { escapeHtml } from "../../shared/html.js";
import { icon } from "../../shared/icons.js";
import { getImprovementPriorityLabel } from "../../shared/labels.js";
import { renderConfidence } from "../matching/insight-components.js";
import { sortByPriority } from "../matching/score-tones.js";

export function createCareerAdviceRenderer({
  openResultsPanel,
  updateMobileResultsBadge,
}) {
  function renderCareerAdviceResult(result) {
    state.currentCareerAdviceResult = result;
    state.currentCvAnalysisResult = null;
    state.currentMatchingResult = null;

    elements.resultsEyebrow.textContent = "CAREER ADVICE";
    elements.resultsTitle.textContent = "Định hướng nghề nghiệp";
    elements.resultsSummary.hidden = true;
    elements.jobSort.disabled = true;
    if (elements.jobPagination) elements.jobPagination.hidden = true;
    elements.backToJobsButton.hidden =
      !state.currentSearchResult || !state.jobs.length;

    elements.jobResults.innerHTML = `
      <section class="insight career-advice-result" aria-label="Kết quả tư vấn nghề nghiệp">
        <header class="career-overview">
          <span class="badge ${result.isPersonalized ? "badge-accent" : ""}">
            ${result.isPersonalized ? "Cá nhân hóa theo CV" : "Tư vấn tổng quát"}
          </span>
          <h3>${escapeHtml(result.careerGoal || "Định hướng nghề nghiệp")}</h3>
          <p>${escapeHtml(result.summary || "Chưa có nhận xét tổng quan.")}</p>
          ${renderConfidence(result.confidence)}
          ${renderTopPrioritySkills(result.topPrioritySkills)}
          ${renderDataQualityWarnings(result.dataQualityWarnings)}
        </header>

        ${renderCareerNextActions(result.nextActions)}
        ${renderCareerRoadmap(result.roadmap)}
        ${renderCareerSkillGaps(result.skillGaps)}
        ${renderCareerRoles(result.recommendedRoles)}
        ${renderPortfolioProjects(result.portfolioProjects)}
      </section>
    `;
    elements.jobResults.scrollTop = 0;

    updateMobileResultsBadge(1);
    openResultsPanel();
  }

  return { renderCareerAdviceResult };
}

function renderSection(title, note, content) {
  return `
    <section class="insight-section">
      <div class="insight-section-header">
        <h3>${escapeHtml(title)}</h3>
        ${note ? `<p>${escapeHtml(note)}</p>` : ""}
      </div>
      ${content}
    </section>
  `;
}

function renderPriority(priority) {
  const value = ["high", "medium", "low"].includes(priority) ? priority : "medium";

  return `
    <span class="priority-badge ${value}">
      ${escapeHtml(getImprovementPriorityLabel(value))}
    </span>
  `;
}

function renderTopPrioritySkills(skills) {
  const items = toArray(skills);
  if (!items.length) return "";

  return `
    <div class="career-skill-chips" aria-label="Kỹ năng cần ưu tiên">
      ${items
        .map((skill, index) => `<span><b>${index + 1}</b>${escapeHtml(skill)}</span>`)
        .join("")}
    </div>
  `;
}

function renderDataQualityWarnings(warnings) {
  const items = toArray(warnings);
  if (!items.length) return "";

  return `
    <div class="alert alert-info" role="note">
      ${icon("info")}
      <div>
        <strong>Lưu ý về dữ liệu đầu vào</strong>
        <ul class="career-warning-list">
          ${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
        </ul>
      </div>
    </div>
  `;
}

function renderCareerRoles(roles) {
  const items = toArray(roles);
  if (!items.length) return "";

  return renderSection(
    "Vị trí nghề nghiệp phù hợp",
    `${items.length} vị trí`,
    `
      <div class="career-card-grid">
        ${items
          .map(
            (role) => `
              <article class="career-card">
                <div class="career-card-header">
                  <h4>${escapeHtml(role.roleTitle)}</h4>
                  <span class="readiness-badge ${escapeHtml(role.readinessLevel)}">
                    ${escapeHtml(getCareerReadinessLabel(role.readinessLevel))}
                  </span>
                </div>
                <p>${escapeHtml(role.rationale)}</p>
                ${renderCareerList("Bằng chứng từ CV", role.cvEvidence)}
                ${renderCareerList("Điểm cần phát triển", role.developmentNeeds)}
              </article>
            `,
          )
          .join("")}
      </div>
    `,
  );
}

function renderCareerSkillGaps(skillGaps) {
  const items = sortByPriority(skillGaps);
  if (!items.length) return "";

  return renderSection(
    "Khoảng trống kỹ năng",
    "Sắp xếp theo mức ưu tiên",
    `
      <div class="career-gap-list">
        ${items
          .map(
            (gap) => `
              <article class="career-gap">
                <div class="career-gap-title">
                  <h4>${escapeHtml(gap.skill)}</h4>
                  ${renderPriority(gap.priority)}
                </div>
                <div class="career-gap-body">
                  <p>${escapeHtml(gap.reason)}</p>
                  ${renderCareerList("Nền tảng hiện tại", gap.currentEvidence)}
                  ${
                    gap.recommendedAction
                      ? `<div class="career-action-box">
                          <strong>Hành động đề xuất</strong>
                          <p>${escapeHtml(gap.recommendedAction)}</p>
                        </div>`
                      : ""
                  }
                </div>
              </article>
            `,
          )
          .join("")}
      </div>
    `,
  );
}

function renderCareerRoadmap(roadmap) {
  const items = toArray(roadmap);
  if (!items.length) return "";

  return renderSection(
    "Lộ trình phát triển",
    `${items.length} giai đoạn`,
    `
      <ol class="career-roadmap">
        ${items
          .map(
            (step, index) => `
              <li class="career-roadmap-step">
                <div class="career-phase" aria-hidden="true">${escapeHtml(step.phase || index + 1)}</div>
                <div class="career-roadmap-content">
                  <div class="career-card-header">
                    <h4>
                      <span class="visually-hidden">Giai đoạn ${escapeHtml(step.phase || index + 1)}: </span>
                      ${escapeHtml(step.title || `Giai đoạn ${step.phase || index + 1}`)}
                    </h4>
                    ${step.timeframe ? `<span class="career-timeframe">${escapeHtml(step.timeframe)}</span>` : ""}
                  </div>
                  ${step.objective ? `<p>${escapeHtml(step.objective)}</p>` : ""}
                  <div class="career-roadmap-lists">
                    ${renderCareerList("Hành động", step.actions)}
                    ${renderCareerList("Tiêu chí hoàn thành", step.successCriteria)}
                  </div>
                </div>
              </li>
            `,
          )
          .join("")}
      </ol>
    `,
  );
}

function renderPortfolioProjects(projects) {
  const items = toArray(projects);
  if (!items.length) return "";

  return renderSection(
    "Dự án portfolio đề xuất",
    null,
    `
      <div class="career-card-grid">
        ${items
          .map(
            (project) => `
              <article class="career-card">
                <h4>${escapeHtml(project.title)}</h4>
                <p>${escapeHtml(project.purpose)}</p>
                ${renderCareerList("Kỹ năng thực hành", project.skillsPracticed)}
                ${renderCareerList("Tính năng gợi ý", project.suggestedFeatures)}
                ${
                  project.expectedDeliverable
                    ? `<div class="career-action-box">
                        <strong>Kết quả đầu ra</strong>
                        <p>${escapeHtml(project.expectedDeliverable)}</p>
                      </div>`
                    : ""
                }
              </article>
            `,
          )
          .join("")}
      </div>
    `,
  );
}

function renderCareerNextActions(actions) {
  const items = sortByPriority(actions);
  if (!items.length) return "";

  return renderSection(
    "Việc nên làm tiếp theo",
    null,
    `
      <ol class="career-next-actions">
        ${items
          .map(
            (item) => `
              <li class="career-next-action">
                ${renderPriority(item.priority)}
                <div>
                  <h4>${escapeHtml(item.action)}</h4>
                  ${item.reason ? `<p>${escapeHtml(item.reason)}</p>` : ""}
                  ${item.timeframe ? `<small>Thời gian: ${escapeHtml(item.timeframe)}</small>` : ""}
                </div>
              </li>
            `,
          )
          .join("")}
      </ol>
    `,
  );
}

function renderCareerList(title, items) {
  const values = toArray(items);
  if (!values.length) return "";

  return `
    <div class="career-list">
      <strong>${escapeHtml(title)}</strong>
      <ul>
        ${values.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
    </div>
  `;
}

function getCareerReadinessLabel(value) {
  const labels = {
    ready: "Sẵn sàng",
    nearly_ready: "Gần sẵn sàng",
    developing: "Đang phát triển",
    exploring: "Đang khám phá",
  };

  return labels[value] ?? "Chưa xác định";
}

function toArray(value) {
  return Array.isArray(value) ? value : [];
}
