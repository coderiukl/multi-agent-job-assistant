import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import { clampMatchingScore } from "../../shared/formatters.js";
import { escapeHtml } from "../../shared/html.js";
import {
  getCvQualityLabel,
  getCvSectionLabel,
  getImprovementPriorityLabel,
} from "../../shared/labels.js";
import {
  renderBreakdownSection,
  renderFindingSection,
  renderScoreOverview,
} from "../matching/insight-components.js";
import { sortByPriority } from "../matching/score-tones.js";

const QUALITY_TONES = {
  excellent: "tone-strong",
  good: "tone-good",
  needs_improvement: "tone-partial",
  weak: "tone-low",
};

export function createCvAnalysisRenderer({
  openResultsPanel,
  updateMobileResultsBadge,
}) {
  function renderCvAnalysisResult(result) {
    state.currentCvAnalysisResult = result;
    state.currentMatchingResult = null;

    const score = clampMatchingScore(result?.overallScore);
    const breakdown = result?.breakdown ?? {};
    const strengths = toArray(result?.strengths);
    const weaknesses = toArray(result?.weaknesses);
    const improvements = sortByPriority(result?.improvements);
    const qualityLevel =
      result?.qualityLevel ?? "needs_improvement";

    elements.resultsEyebrow.textContent = "CV ANALYSIS";
    elements.resultsTitle.textContent = "Phân tích CV";
    elements.resultsSummary.hidden = true;
    elements.jobSort.disabled = true;
    if (elements.jobPagination) elements.jobPagination.hidden = true;
    elements.backToJobsButton.hidden =
      !state.currentSearchResult || !state.jobs.length;

    updateMobileResultsBadge(1);
    openResultsPanel();

    elements.jobResults.innerHTML = `
      <section class="insight cv-analysis-result" aria-label="Kết quả phân tích CV">
        ${renderScoreOverview({
          score,
          scoreLabel: "Điểm chất lượng CV",
          badgeLabel: getCvQualityLabel(qualityLevel),
          badgeTone: QUALITY_TONES[qualityLevel] ?? "tone-partial",
          title: "Chất lượng nội dung CV",
          summary: result?.summary,
          confidence: result?.confidence,
        })}

        <section class="insight-section" aria-labelledby="cv-improvements-title">
          <div class="insight-section-header">
            <h3 id="cv-improvements-title">Đề xuất cải thiện</h3>
            <p>Sắp xếp theo mức ưu tiên</p>
          </div>
          ${
            improvements.length
              ? `<div class="improvement-list">
                  ${improvements.map(renderImprovement).join("")}
                </div>`
              : `<p class="insight-empty">Chưa có đề xuất cải thiện.</p>`
          }
        </section>

        <div class="insight-columns">
          ${renderFindingSection({
            title: "Điểm mạnh",
            items: strengths,
            variant: "is-strength",
            emptyMessage: "Chưa xác định được điểm mạnh nổi bật.",
            renderItem: renderFinding,
          })}
          ${renderFindingSection({
            title: "Điểm cần cải thiện",
            items: weaknesses,
            variant: "is-gap",
            emptyMessage: "Chưa ghi nhận điểm yếu quan trọng.",
            renderItem: renderFinding,
          })}
        </div>

        ${renderBreakdownSection("Điểm thành phần", [
          ["Độ đầy đủ", breakdown.completeness],
          ["Giới thiệu bản thân", breakdown.professionalSummary],
          ["Kỹ năng", breakdown.skills],
          ["Kinh nghiệm", breakdown.workExperience],
          ["Dự án", breakdown.projects],
          ["Học vấn & chứng chỉ", breakdown.educationAndCredentials],
        ])}
      </section>
    `;
    elements.jobResults.scrollTop = 0;
  }

  return { renderCvAnalysisResult };
}

function renderFinding(item) {
  const evidence = toArray(item?.cvEvidence);

  return `
    <strong>${escapeHtml(item?.finding || "Chưa có nhận xét.")}</strong>
    <span class="finding-meta">${escapeHtml(getCvSectionLabel(item?.section))}</span>
    ${
      evidence.length
        ? `<ul class="finding-evidence" aria-label="Bằng chứng từ CV">
            ${evidence
              .map((value) => `<li>${escapeHtml(value)}</li>`)
              .join("")}
          </ul>`
        : ""
    }
  `;
}

function renderImprovement(item) {
  const priority = ["high", "medium", "low"].includes(item?.priority)
    ? item.priority
    : "medium";

  return `
    <article class="cv-improvement-item priority-${priority}">
      <header>
        <span class="priority-badge ${priority}">
          ${escapeHtml(getImprovementPriorityLabel(priority))}
        </span>
        <span class="section-label">
          ${escapeHtml(getCvSectionLabel(item?.section))}
        </span>
      </header>

      <h4>${escapeHtml(item?.issue || "Nội dung cần cải thiện")}</h4>
      <p>${escapeHtml(item?.suggestion || "Chưa có hướng dẫn cụ thể.")}</p>
      ${
        item?.example
          ? `<div class="cv-improvement-example">
              <strong>Ví dụ tham khảo</strong>
              <p>${escapeHtml(item.example)}</p>
            </div>`
          : ""
      }
    </article>
  `;
}

function toArray(value) {
  return Array.isArray(value) ? value : [];
}
