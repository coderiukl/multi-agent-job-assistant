import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import { escapeHtml } from "../../shared/html.js";
import { getImprovementPriorityLabel } from "../../shared/labels.js";

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

    const confidence =
      result.confidence === null
        ? "Chưa xác định"
        : `${Math.round(result.confidence * 100)}%`;

    elements.jobResults.innerHTML = `
      <section
        class="career-advice-result"
        aria-label="Kết quả tư vấn nghề nghiệp"
      >
        <header class="career-advice-overview">
          <span class="career-personalization-badge ${
            result.isPersonalized ? "personalized" : "general"
          }">
            ${
              result.isPersonalized
                ? "Cá nhân hóa theo CV"
                : "Tư vấn tổng quát"
            }
          </span>

          <h3>${escapeHtml(
            result.careerGoal || "Định hướng nghề nghiệp",
          )}</h3>
          <p>${escapeHtml(result.summary)}</p>
          <span class="career-confidence">
            Độ tin cậy: ${escapeHtml(confidence)}
          </span>
        </header>

        ${renderTopPrioritySkills(result.topPrioritySkills)}
        ${renderCareerRoles(result.recommendedRoles)}
        ${renderCareerSkillGaps(result.skillGaps)}
        ${renderCareerRoadmap(result.roadmap)}
        ${renderPortfolioProjects(result.portfolioProjects)}
        ${renderCareerNextActions(result.nextActions)}
      </section>
    `;

    updateMobileResultsBadge(1);
    openResultsPanel();
  }

  return { renderCareerAdviceResult };
}

function renderTopPrioritySkills(skills) {
  const items = toArray(skills);
  if (!items.length) return "";

  return `
    <section class="career-section">
      <h3>Kỹ năng cần ưu tiên</h3>
      <div class="career-skill-chips">
        ${items.map((skill) => `<span>${escapeHtml(skill)}</span>`).join("")}
      </div>
    </section>
  `;
}

function renderCareerRoles(roles) {
  const items = toArray(roles);
  if (!items.length) return "";

  return `
    <section class="career-section">
      <h3>Vị trí nghề nghiệp phù hợp</h3>
      <div class="career-role-grid">
        ${items
          .map(
            (role) => `
              <article class="career-role-card">
                <div class="career-card-header">
                  <h4>${escapeHtml(role.roleTitle)}</h4>
                  <span class="readiness-badge ${escapeHtml(
                    role.readinessLevel,
                  )}">
                    ${escapeHtml(
                      getCareerReadinessLabel(role.readinessLevel),
                    )}
                  </span>
                </div>
                <p>${escapeHtml(role.rationale)}</p>
                ${renderCareerList("Bằng chứng từ CV", role.cvEvidence)}
                ${renderCareerList(
                  "Điểm cần phát triển",
                  role.developmentNeeds,
                )}
              </article>
            `,
          )
          .join("")}
      </div>
    </section>
  `;
}

function renderCareerSkillGaps(skillGaps) {
  const items = toArray(skillGaps);
  if (!items.length) return "";

  return `
    <section class="career-section">
      <h3>Khoảng trống kỹ năng</h3>
      <div class="career-gap-list">
        ${items
          .map(
            (gap) => `
              <article class="career-gap-card">
                <div class="career-card-header">
                  <h4>${escapeHtml(gap.skill)}</h4>
                  <span class="career-priority priority-${escapeHtml(
                    gap.priority,
                  )}">
                    ${escapeHtml(
                      getImprovementPriorityLabel(gap.priority),
                    )}
                  </span>
                </div>
                <p>${escapeHtml(gap.reason)}</p>
                ${renderCareerList(
                  "Nền tảng hiện tại",
                  gap.currentEvidence,
                )}
                <div class="career-action-box">
                  <strong>Hành động đề xuất</strong>
                  <p>${escapeHtml(gap.recommendedAction)}</p>
                </div>
              </article>
            `,
          )
          .join("")}
      </div>
    </section>
  `;
}

function renderCareerRoadmap(roadmap) {
  const items = toArray(roadmap);
  if (!items.length) return "";

  return `
    <section class="career-section">
      <h3>Lộ trình phát triển</h3>
      <div class="career-roadmap">
        ${items
          .map(
            (step) => `
              <article class="career-roadmap-step">
                <div class="career-phase">${escapeHtml(step.phase)}</div>
                <div class="career-roadmap-content">
                  <div class="career-card-header">
                    <h4>${escapeHtml(step.title)}</h4>
                    <span>${escapeHtml(step.timeframe)}</span>
                  </div>
                  <p>${escapeHtml(step.objective)}</p>
                  ${renderCareerList("Hành động", step.actions)}
                  ${renderCareerList(
                    "Tiêu chí hoàn thành",
                    step.successCriteria,
                  )}
                </div>
              </article>
            `,
          )
          .join("")}
      </div>
    </section>
  `;
}

function renderPortfolioProjects(projects) {
  const items = toArray(projects);
  if (!items.length) return "";

  return `
    <section class="career-section">
      <h3>Dự án portfolio đề xuất</h3>
      <div class="career-project-grid">
        ${items
          .map(
            (project) => `
              <article class="career-project-card">
                <h4>${escapeHtml(project.title)}</h4>
                <p>${escapeHtml(project.purpose)}</p>
                ${renderCareerList(
                  "Kỹ năng thực hành",
                  project.skillsPracticed,
                )}
                ${renderCareerList(
                  "Tính năng gợi ý",
                  project.suggestedFeatures,
                )}
                <div class="career-action-box">
                  <strong>Kết quả đầu ra</strong>
                  <p>${escapeHtml(project.expectedDeliverable)}</p>
                </div>
              </article>
            `,
          )
          .join("")}
      </div>
    </section>
  `;
}

function renderCareerNextActions(actions) {
  const items = toArray(actions);
  if (!items.length) return "";

  return `
    <section class="career-section">
      <h3>Việc nên làm tiếp theo</h3>
      <div class="career-next-actions">
        ${items
          .map(
            (item) => `
              <article class="career-next-action">
                <span class="career-priority priority-${escapeHtml(
                  item.priority,
                )}">
                  ${escapeHtml(
                    getImprovementPriorityLabel(item.priority),
                  )}
                </span>
                <div>
                  <h4>${escapeHtml(item.action)}</h4>
                  <p>${escapeHtml(item.reason)}</p>
                  ${
                    item.timeframe
                      ? `<small>Thời gian: ${escapeHtml(
                          item.timeframe,
                        )}</small>`
                      : ""
                  }
                </div>
              </article>
            `,
          )
          .join("")}
      </div>
    </section>
  `;
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
