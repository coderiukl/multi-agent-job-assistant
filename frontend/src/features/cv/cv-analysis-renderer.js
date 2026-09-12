import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import { clampMatchingScore } from "../../shared/formatters.js";
import { escapeHtml } from "../../shared/html.js";
import {
  getCvQualityBadgeClass,
  getCvQualityLabel,
  getCvSectionLabel,
  getImprovementPriorityLabel,
} from "../../shared/labels.js";

export function createCvAnalysisRenderer({
  openResultsPanel,
  renderBreakdownItem,
  updateMobileResultsBadge,
}) {
  function renderCvAnalysisResult(result) {
    state.currentCvAnalysisResult = result;
    state.currentMatchingResult = null;

    const score = clampMatchingScore(result?.overallScore);
    const breakdown = result?.breakdown ?? {};
    const strengths = toArray(result?.strengths);
    const weaknesses = toArray(result?.weaknesses);
    const improvements = toArray(result?.improvements);
    const qualityLevel =
      result?.qualityLevel ?? "needs_improvement";

    elements.resultsEyebrow.textContent = "CV ANALYSIS";
    elements.resultsTitle.textContent = "Phân tích CV";
    elements.resultsSummary.hidden = true;
    elements.jobSort.disabled = true;
    elements.backToJobsButton.hidden =
      !state.currentSearchResult || !state.jobs.length;

    updateMobileResultsBadge(1);
    openResultsPanel();

    elements.jobResults.innerHTML = `
      <section
        class="matching-result cv-analysis-result"
        aria-label="Kết quả phân tích CV"
      >
        <header class="matching-overview">
          <div
            class="matching-score-ring"
            style="--matching-score: ${score}"
            aria-label="Điểm chất lượng CV ${score.toFixed(2)} trên 100"
          >
            <strong>${score.toFixed(2)}</strong>
            <span>/100</span>
          </div>

          <div class="matching-summary">
            <span
              class="recommendation-badge ${getCvQualityBadgeClass(
                qualityLevel,
              )}"
            >
              ${escapeHtml(getCvQualityLabel(qualityLevel))}
            </span>

            <h3>Chất lượng nội dung CV</h3>
            <p>
              ${escapeHtml(
                result?.summary || "Chưa có nhận xét tổng quan.",
              )}
            </p>
            ${renderConfidence(result?.confidence)}
          </div>
        </header>

        <section class="matching-section">
          <h3>Điểm thành phần</h3>
          <div class="breakdown-grid">
            ${renderBreakdownItem("Độ đầy đủ", breakdown.completeness)}
            ${renderBreakdownItem(
              "Giới thiệu bản thân",
              breakdown.professionalSummary,
            )}
            ${renderBreakdownItem("Kỹ năng", breakdown.skills)}
            ${renderBreakdownItem("Kinh nghiệm", breakdown.workExperience)}
            ${renderBreakdownItem("Dự án", breakdown.projects)}
            ${renderBreakdownItem(
              "Học vấn & chứng chỉ",
              breakdown.educationAndCredentials,
            )}
          </div>
        </section>

        <div class="matching-columns">
          ${renderFindingList(
            "Điểm mạnh",
            strengths,
            "strength",
            "Chưa xác định được điểm mạnh nổi bật.",
          )}
          ${renderFindingList(
            "Điểm cần cải thiện",
            weaknesses,
            "gap",
            "Chưa ghi nhận điểm yếu quan trọng.",
          )}
        </div>

        <section class="matching-section cv-improvements">
          <h3>Đề xuất cải thiện</h3>
          ${
            improvements.length
              ? `<div class="cv-improvement-list">
                  ${improvements.map(renderImprovement).join("")}
                </div>`
              : `<p class="matching-empty-text">
                  Chưa có đề xuất cải thiện.
                </p>`
          }
        </section>
      </section>
    `;
  }

  return { renderCvAnalysisResult };
}

function renderConfidence(confidence) {
  if (confidence === null || confidence === undefined) {
    return "";
  }

  return `
    <small>
      Độ tin cậy đánh giá: ${Math.round(confidence * 100)}%
    </small>
  `;
}

function renderFindingList(title, items, variant, emptyMessage) {
  return `
    <section class="matching-list-card ${escapeHtml(variant)}">
      <h3>${escapeHtml(title)}</h3>
      ${
        items.length
          ? `<ul class="cv-finding-list">
              ${items.map(renderFinding).join("")}
            </ul>`
          : `<p>${escapeHtml(emptyMessage)}</p>`
      }
    </section>
  `;
}

function renderFinding(item) {
  const evidence = toArray(item?.cvEvidence);

  return `
    <li>
      <strong>
        ${escapeHtml(item?.finding || "Chưa có nhận xét.")}
      </strong>
      <span class="cv-section-label">
        ${escapeHtml(getCvSectionLabel(item?.section))}
      </span>
      ${
        evidence.length
          ? `<ul class="cv-finding-evidence">
              ${evidence
                .map((value) => `<li>${escapeHtml(value)}</li>`)
                .join("")}
            </ul>`
          : ""
      }
    </li>
  `;
}

function renderImprovement(item) {
  const priority = item?.priority ?? "medium";

  return `
    <article class="cv-improvement-item priority-${escapeHtml(priority)}">
      <header>
        <span class="cv-priority-badge ${escapeHtml(priority)}">
          ${escapeHtml(getImprovementPriorityLabel(priority))}
        </span>
        <span class="cv-section-label">
          ${escapeHtml(getCvSectionLabel(item?.section))}
        </span>
      </header>

      <h4>${escapeHtml(item?.issue || "Nội dung cần cải thiện")}</h4>
      <p>
        ${escapeHtml(
          item?.suggestion || "Chưa có hướng dẫn cụ thể.",
        )}
      </p>
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
