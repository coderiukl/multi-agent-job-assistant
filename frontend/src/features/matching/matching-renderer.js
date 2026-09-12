import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import { clampMatchingScore } from "../../shared/formatters.js";
import { escapeHtml } from "../../shared/html.js";
import {
  getEvidenceStatusLabel,
  getRecommendationLabel,
} from "../../shared/labels.js";

export function createMatchingRenderer({
  openResultsPanel,
  updateMobileResultsBadge,
}) {
  function renderJobMatchingResult(result) {
    state.currentMatchingResult = result;

    const score = clampMatchingScore(result?.overallScore);
    const breakdown = result?.breakdown ?? {};
    const strengths = toArray(result?.strengths);
    const gaps = toArray(result?.gaps);
    const evidence = toArray(result?.evidence);
    const actionPlan = createActionPlan({
      score,
      gaps,
      evidence,
      recommendation: result?.recommendation,
    });

    elements.resultsEyebrow.textContent = "CV · JOB MATCHING";
    elements.resultsTitle.textContent = "Kết quả so khớp";
    elements.resultsSummary.hidden = true;
    elements.jobSort.disabled = true;
    elements.backToJobsButton.hidden =
      !state.currentSearchResult || !state.jobs.length;

    updateMobileResultsBadge(1);
    openResultsPanel();

    elements.jobResults.innerHTML = `
      <section class="matching-result" aria-label="Kết quả so khớp CV">
        <header class="matching-overview">
          <div
            class="matching-score-ring"
            style="--matching-score: ${score}"
            aria-label="Điểm phù hợp ${score.toFixed(2)} trên 100"
          >
            <strong>${score.toFixed(2)}</strong>
            <span>/100</span>
          </div>

          <div class="matching-summary">
            <span class="recommendation-badge ${escapeHtml(
              result?.recommendation || "low_match",
            )}">
              ${escapeHtml(
                getRecommendationLabel(result?.recommendation),
              )}
            </span>

            <h3>Mức độ phù hợp tổng thể</h3>
            <p>
              ${escapeHtml(
                result?.summary || "Chưa có nhận xét tổng quan.",
              )}
            </p>
            ${renderConfidence(result?.confidence)}
          </div>
        </header>

        <section class="matching-section action-plan">
          <div>
            <span class="section-kicker">Hành động tiếp theo</span>
            <h3>Ưu tiên trước khi ứng tuyển</h3>
          </div>
          <ol>
            ${actionPlan
              .map((item) => `<li>${escapeHtml(item)}</li>`)
              .join("")}
          </ol>
        </section>

        <section class="matching-section">
          <h3>Điểm thành phần</h3>
          <div class="breakdown-grid">
            ${renderBreakdownItem(
              "Kỹ năng chuyên môn",
              breakdown.technicalSkills,
            )}
            ${renderBreakdownItem("Kinh nghiệm", breakdown.experience)}
            ${renderBreakdownItem("Dự án", breakdown.projects)}
            ${renderBreakdownItem("Học vấn", breakdown.education)}
            ${renderBreakdownItem(
              "Ngoại ngữ & chứng chỉ",
              breakdown.languagesAndCertifications,
            )}
          </div>
        </section>

        <div class="matching-columns">
          ${renderMatchingList(
            "Điểm mạnh",
            strengths,
            "strength",
            "Chưa xác định được điểm mạnh nổi bật.",
          )}
          ${renderMatchingList(
            "Khoảng thiếu",
            gaps,
            "gap",
            "Không có khoảng thiếu quan trọng được ghi nhận.",
          )}
        </div>

        <section class="matching-section evidence-section">
          <h3>Bằng chứng đánh giá</h3>
          ${
            evidence.length
              ? `<div class="evidence-list">
                  ${evidence.map(renderEvidenceItem).join("")}
                </div>`
              : `<p class="matching-empty-text">
                  Chưa có bằng chứng chi tiết.
                </p>`
          }
        </section>
      </section>
    `;
  }

  return {
    renderBreakdownItem,
    renderJobMatchingResult,
  };
}

export function renderBreakdownItem(label, value) {
  const score = clampMatchingScore(value);

  return `
    <article class="breakdown-item">
      <div>
        <span>${escapeHtml(label)}</span>
        <strong>${score.toFixed(0)}</strong>
      </div>
      <div class="score-track" aria-hidden="true">
        <span style="width: ${score}%"></span>
      </div>
    </article>
  `;
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

function createActionPlan({
  score,
  gaps,
  evidence,
  recommendation,
}) {
  const missingEvidence = evidence
    .filter((item) => item?.status === "missing")
    .map((item) => item.requirement)
    .filter(Boolean);

  const plan = [];

  if (score >= 80 || recommendation === "strong_match") {
    plan.push(
      "Chuẩn bị nộp hồ sơ, ưu tiên làm nổi bật các điểm mạnh đang khớp với JD.",
    );
  } else if (score >= 60) {
    plan.push(
      "Ứng tuyển được, nhưng nên chỉnh CV để nhấn mạnh kinh nghiệm gần nhất với vai trò.",
    );
  } else {
    plan.push(
      "Khoan ứng tuyển ngay; hãy bổ sung bằng chứng kỹ năng trước để tăng tỷ lệ phản hồi.",
    );
  }

  if (missingEvidence.length) {
    plan.push(
      `Bổ sung ví dụ cụ thể cho: ${missingEvidence.slice(0, 2).join(", ")}.`,
    );
  } else if (gaps.length) {
    plan.push(
      `Xử lý khoảng thiếu nổi bật: ${gaps.slice(0, 2).join(", ")}.`,
    );
  } else {
    plan.push(
      "Giữ CV ngắn gọn và dùng từ khóa giống JD ở phần kinh nghiệm gần nhất.",
    );
  }

  plan.push(
    "Chuẩn bị 2-3 câu chuyện phỏng vấn có số liệu, vai trò cá nhân và kết quả rõ ràng.",
  );

  return plan;
}

function renderMatchingList(
  title,
  items,
  variant,
  emptyMessage,
) {
  return `
    <section class="matching-list-card ${escapeHtml(variant)}">
      <h3>${escapeHtml(title)}</h3>
      ${
        items.length
          ? `<ul>
              ${items
                .map((item) => `<li>${escapeHtml(item)}</li>`)
                .join("")}
            </ul>`
          : `<p>${escapeHtml(emptyMessage)}</p>`
      }
    </section>
  `;
}

function renderEvidenceItem(item) {
  const cvEvidence = toArray(item?.cvEvidence);

  return `
    <details class="evidence-item">
      <summary>
        <span class="evidence-status ${escapeHtml(item?.status || "missing")}">
          ${escapeHtml(getEvidenceStatusLabel(item?.status))}
        </span>
        <span>${escapeHtml(item?.requirement || "Yêu cầu công việc")}</span>
      </summary>

      <div class="evidence-content">
        <p>${escapeHtml(item?.explanation || "Chưa có giải thích.")}</p>
        ${
          cvEvidence.length
            ? `<strong>Bằng chứng từ CV</strong>
              <ul>
                ${cvEvidence
                  .map((evidence) => `<li>${escapeHtml(evidence)}</li>`)
                  .join("")}
              </ul>`
            : `<span class="no-cv-evidence">
                Không tìm thấy bằng chứng tương ứng trong CV.
              </span>`
        }
      </div>
    </details>
  `;
}

function toArray(value) {
  return Array.isArray(value) ? value : [];
}
