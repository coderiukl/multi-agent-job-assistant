import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import { clampMatchingScore } from "../../shared/formatters.js";
import { escapeHtml } from "../../shared/html.js";
import { icon } from "../../shared/icons.js";
import {
  getEvidenceStatusLabel,
  getRecommendationLabel,
} from "../../shared/labels.js";
import {
  renderBreakdownItem,
  renderBreakdownSection,
  renderFindingSection,
  renderScoreOverview,
} from "./insight-components.js";
import {
  getRecommendationTone,
  groupEvidenceByStatus,
} from "./score-tones.js";

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
    if (elements.jobPagination) elements.jobPagination.hidden = true;
    elements.backToJobsButton.hidden =
      !state.currentSearchResult || !state.jobs.length;

    updateMobileResultsBadge(1);
    openResultsPanel();

    elements.jobResults.innerHTML = `
      <section class="insight matching-result" aria-label="Kết quả so khớp CV">
        ${renderScoreOverview({
          score,
          scoreLabel: "Điểm phù hợp",
          badgeLabel: getRecommendationLabel(result?.recommendation),
          badgeTone: getRecommendationTone(result?.recommendation),
          title: "Mức độ phù hợp tổng thể",
          summary: result?.summary,
          confidence: result?.confidence,
        })}

        <section class="action-plan" aria-labelledby="action-plan-title">
          <p class="eyebrow">Hành động tiếp theo</p>
          <h3 id="action-plan-title">Ưu tiên trước khi ứng tuyển</h3>
          <ol>
            ${actionPlan
              .map((item) => `<li>${escapeHtml(item)}</li>`)
              .join("")}
          </ol>
          <p class="action-plan-note">
            Tổng hợp từ điểm phù hợp và các yêu cầu còn thiếu trong kết quả so khớp.
          </p>
        </section>

        ${renderRequirementCoverage(evidence)}

        <div class="insight-columns">
          ${renderFindingSection({
            title: "Điểm mạnh",
            items: strengths,
            variant: "is-strength",
            emptyMessage: "Chưa xác định được điểm mạnh nổi bật.",
          })}
          ${renderFindingSection({
            title: "Khoảng thiếu",
            items: gaps,
            variant: "is-gap",
            emptyMessage: "Không có khoảng thiếu quan trọng được ghi nhận.",
          })}
        </div>

        ${renderBreakdownSection("Điểm thành phần", [
          ["Kỹ năng chuyên môn", breakdown.technicalSkills],
          ["Kinh nghiệm", breakdown.experience],
          ["Dự án", breakdown.projects],
          ["Học vấn", breakdown.education],
          ["Ngoại ngữ & chứng chỉ", breakdown.languagesAndCertifications],
        ])}
      </section>
    `;
    elements.jobResults.scrollTop = 0;
  }

  return {
    renderBreakdownItem,
    renderJobMatchingResult,
  };
}

export { renderBreakdownItem };

/**
 * Requirement coverage: a proportional bar of matched / partial / missing
 * requirements (counts straight from `evidence[].status`), followed by the
 * evidence grouped so that missing requirements come first.
 */
function renderRequirementCoverage(evidence) {
  if (!evidence.length) {
    return `
      <section class="insight-section">
        <h3>Yêu cầu công việc</h3>
        <p class="insight-empty">Chưa có bằng chứng chi tiết cho từng yêu cầu.</p>
      </section>
    `;
  }

  const groups = groupEvidenceByStatus(evidence);
  const total = evidence.length;
  const legendOrder = ["matched", "partial", "missing", "not_applicable"];
  const counts = Object.fromEntries(
    groups.map((group) => [group.status, group.items.length]),
  );

  return `
    <section class="insight-section" aria-labelledby="coverage-title">
      <div class="insight-section-header">
        <h3 id="coverage-title">Yêu cầu công việc</h3>
        <p>${counts.matched ?? 0}/${total} đáp ứng đầy đủ</p>
      </div>

      <div class="coverage-bar" aria-hidden="true">
        ${legendOrder
          .filter((status) => counts[status])
          .map(
            (status) =>
              `<span class="is-${status}" style="flex: ${counts[status]}"></span>`,
          )
          .join("")}
      </div>

      <ul class="coverage-legend">
        ${legendOrder
          .filter((status) => counts[status])
          .map(
            (status) => `
              <li class="is-${status}">
                ${escapeHtml(getEvidenceStatusLabel(status))}
                <strong>${counts[status]}</strong>
              </li>
            `,
          )
          .join("")}
      </ul>

      ${groups
        .map(
          (group) => `
            <div class="evidence-group">
              <p class="evidence-group-title">
                ${escapeHtml(getEvidenceStatusLabel(group.status))} · ${group.items.length}
              </p>
              <div class="evidence-list">
                ${group.items.map(renderEvidenceItem).join("")}
              </div>
            </div>
          `,
        )
        .join("")}
    </section>
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

function renderEvidenceItem(item) {
  const cvEvidence = toArray(item?.cvEvidence);
  const status = item?.status || "missing";

  return `
    <details class="evidence-item">
      <summary>
        <span class="evidence-status ${escapeHtml(status)}">
          ${escapeHtml(getEvidenceStatusLabel(status))}
        </span>
        <span>${escapeHtml(item?.requirement || "Yêu cầu công việc")}</span>
        ${icon("chevron-down")}
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
