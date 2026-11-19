import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import {
  formatDate,
  formatSalary,
  formatScore,
} from "../../shared/formatters.js";
import { escapeHtml, safeExternalUrl } from "../../shared/html.js";
import { icon } from "../../shared/icons.js";
import {
  getEmploymentTypeLabel,
  getSeniorityLabel,
  getWorkModeLabel,
} from "../../shared/labels.js";
import { renderJobDescription } from "./job-description.js";

export function createJobRenderer({
  closeJobDetail,
  generateCoverLetterForJob,
  matchSelectedJob,
}) {
  const UNKNOWN_LABEL = "Không xác định";

  function renderMetaItem(value, className = "") {
    if (!value || value === UNKNOWN_LABEL) {
      return "";
    }

    return `<li class="${className}">${escapeHtml(value)}</li>`;
  }

  function renderDetailItem(label, value, className = "") {
    if (!value || value === UNKNOWN_LABEL) {
      return "";
    }

    return `
      <div>
        <dt>${escapeHtml(label)}</dt>
        <dd class="${className}">${escapeHtml(value)}</dd>
      </div>
    `;
  }

  function renderSkillChips(skills) {
    if (!skills.length) {
      return "";
    }

    return `
      <div class="skill-list">
        ${skills
          .map((skill) => `<span class="skill-chip">${escapeHtml(skill)}</span>`)
          .join("")}
      </div>
    `;
  }

  function getMatchTone(value) {
    const number = Number(value);

    if (!Number.isFinite(number)) {
      return "is-low";
    }

    if (number >= 0.78) {
      return "is-strong";
    }

    return number >= 0.58 ? "is-good" : "is-low";
  }

  function getMatchLabel(value) {
    const labels = {
      "is-strong": "rất liên quan",
      "is-good": "đáng xem",
      "is-low": "liên quan thấp",
    };

    return labels[getMatchTone(value)];
  }

  /**
   * `score.final` is the search ranking score (0–1) for the query, not a
   * CV match. It is labelled as relevance to avoid implying a CV assessment.
   */
  function renderRelevance(value) {
    const percent = Number.parseInt(formatScore(value), 10) || 0;
    const tone = getMatchTone(value);

    return `
      <div class="relevance ${tone}" title="Độ liên quan với yêu cầu tìm kiếm">
        <span class="relevance-value">${percent}%</span>
        <span class="relevance-bar" aria-hidden="true">
          <span style="--value: ${percent}"></span>
        </span>
        <span class="relevance-label">${escapeHtml(getMatchLabel(value))}</span>
        <span class="visually-hidden">Độ liên quan ${percent} phần trăm</span>
      </div>
    `;
  }

  function renderJobCard(hit, index = 0) {
    const job = hit?.job ?? {};
    const score = hit?.score ?? {};
    const reasons = Array.isArray(hit?.reasons)
      ? hit.reasons.slice(0, 3)
      : [];
    const skills = Array.isArray(job.skills)
      ? job.skills.slice(0, 7)
      : [];
    const jobId = escapeHtml(String(job.job_id ?? ""));
    const sourceUrl = safeExternalUrl(job.source_url);
    const salary = formatSalary(job);
    const companyLine = [job.company || "Chưa có công ty", job.location]
      .filter(Boolean)
      .join(" · ");

    return `
      <article class="job-card" style="animation-delay: ${Math.min(index, 8) * 30}ms">
        <header class="job-card-header">
          <div class="job-heading">
            <h3 class="job-title">
              <button type="button" class="job-title-button"
                data-action="view-job" data-job-id="${jobId}">
                ${escapeHtml(job.title || "Chưa có chức danh")}
              </button>
            </h3>
            <p class="job-company">${escapeHtml(companyLine)}</p>
          </div>
          ${renderRelevance(score.final)}
        </header>

        <ul class="job-meta" aria-label="Thông tin công việc">
          ${salary ? renderMetaItem(salary, "is-salary") : ""}
          ${renderMetaItem(getSeniorityLabel(job.seniority_level))}
          ${renderMetaItem(getWorkModeLabel(job.work_mode))}
          ${renderMetaItem(getEmploymentTypeLabel(job.employment_type))}
        </ul>

        ${renderSkillChips(skills)}

        ${
          reasons.length
            ? `<ul class="reason-list" aria-label="Vì sao công việc này được đề xuất">
                ${reasons
                  .map((reason) => `<li>${escapeHtml(reason)}</li>`)
                  .join("")}
              </ul>`
            : ""
        }

        <footer class="job-card-actions">
          <button type="button" class="btn btn-ghost btn-sm"
            data-action="match-job" data-job-id="${jobId}">
            ${icon("target")} So khớp CV
          </button>
          <button type="button" class="btn btn-ghost btn-sm"
            data-action="cover-letter-job" data-job-id="${jobId}">
            ${icon("mail")} Viết thư
          </button>
          <button type="button" class="btn btn-ghost btn-sm"
            data-action="view-job" data-job-id="${jobId}">
            Chi tiết
          </button>
          ${
            sourceUrl
              ? `<a class="btn btn-ghost btn-sm" href="${escapeHtml(sourceUrl)}"
                    target="_blank" rel="noopener noreferrer">
                  Ứng tuyển ${icon("external")}
                  <span class="visually-hidden">(mở trong thẻ mới)</span>
                </a>`
              : ""
          }
        </footer>
      </article>
    `;
  }

  function openJobDetail(hit) {
    const job = hit?.job ?? {};
    const sourceUrl = safeExternalUrl(job.source_url);

    state.selectedJob = hit;
    state.lastFocusedBeforeDrawer = document.activeElement;
    const salary = formatSalary(job);
    const skills = Array.isArray(job.skills) ? job.skills : [];

    elements.jobDetailContent.innerHTML = `
      <section class="drawer-job-heading">
        <h2>${escapeHtml(job.title || "Công việc")}</h2>
        <p>${escapeHtml(job.company || "Chưa có công ty")}</p>
      </section>

      <dl class="detail-grid">
        ${renderDetailItem("Mức lương", salary, "is-salary")}
        ${renderDetailItem("Địa điểm", job.location)}
        ${renderDetailItem("Cấp độ", getSeniorityLabel(job.seniority_level))}
        ${renderDetailItem("Hình thức", getWorkModeLabel(job.work_mode))}
        ${renderDetailItem("Loại việc", getEmploymentTypeLabel(job.employment_type))}
        ${renderDetailItem("Ngày đăng", formatDate(job.posted_at))}
        ${renderDetailItem("Nguồn", job.source)}
      </dl>

      ${
        skills.length
          ? `<section class="drawer-section">
              <h3>Kỹ năng yêu cầu</h3>
              ${renderSkillChips(skills)}
            </section>`
          : ""
      }

      ${
        Array.isArray(hit?.reasons) && hit.reasons.length
          ? `<section class="drawer-section">
              <h3>Vì sao được đề xuất</h3>
              <ul class="reason-list">
                ${hit.reasons
                  .map((reason) => `<li>${escapeHtml(reason)}</li>`)
                  .join("")}
              </ul>
            </section>`
          : ""
      }

      <section class="drawer-section">
        <h3>Mô tả công việc</h3>
        ${renderJobDescription(job.description)}
      </section>

      <div class="drawer-actions">
        <button type="button" class="btn btn-primary" id="match-drawer-job">
          ${icon("target")} So khớp với CV
        </button>
        <button type="button" class="btn btn-outline" id="cover-letter-drawer-job">
          ${icon("mail")} Viết thư ứng tuyển
        </button>
        ${
          sourceUrl
            ? `<a class="btn btn-ghost" href="${escapeHtml(sourceUrl)}"
                  target="_blank" rel="noopener noreferrer">
                Trang ứng tuyển ${icon("external")}
                <span class="visually-hidden">(mở trong thẻ mới)</span>
              </a>`
            : ""
        }
        <button type="button" class="btn btn-ghost" id="close-drawer-action">
          Đóng
        </button>
      </div>
    `;

    elements.jobDetailContent
      .querySelector("#cover-letter-drawer-job")
      ?.addEventListener("click", () => generateCoverLetterForJob(hit));
    elements.jobDetailContent
      .querySelector("#match-drawer-job")
      ?.addEventListener("click", () => matchSelectedJob(hit));
    elements.jobDetailContent
      .querySelector("#close-drawer-action")
      ?.addEventListener("click", closeJobDetail);

    elements.jobDetailOverlay.hidden = false;
    elements.jobDetailDrawer.classList.add("is-open");
    elements.jobDetailDrawer.setAttribute("aria-hidden", "false");

    requestAnimationFrame(() => {
      elements.closeJobDetailButton.focus();
    });
  }

  function renderJobDescriptionComposerSummary(job) {
    if (
      !state.matchingMode ||
      !job ||
      !elements.jobDescriptionSummary
    ) {
      elements.jobDescriptionSummary.hidden = true;
      elements.jobDescriptionSummary.innerHTML = "";
      elements.jobDescriptionInput.hidden = false;

      if (elements.editJdButton) {
        elements.editJdButton.hidden = true;
      }
      return;
    }

    const skills = Array.isArray(job.skills) ? job.skills.slice(0, 4) : [];
    const salary = formatSalary(job);

    elements.jobDescriptionSummary.hidden = false;
    elements.jobDescriptionInput.hidden = true;

    if (elements.editJdButton) {
      elements.editJdButton.hidden = false;
    }

    elements.jobDescriptionSummary.innerHTML = `
      <div>
        <span class="jd-summary-kicker">JD đã tự điền</span>
        <strong>${escapeHtml(job.title || "Công việc đang chọn")}</strong>
        <small>${escapeHtml(job.company || "Chưa có công ty")}</small>
      </div>
      <dl>
        ${renderSummaryMetric("Địa điểm", job.location)}
        ${renderSummaryMetric("Hình thức", getWorkModeLabel(job.work_mode))}
        ${renderSummaryMetric("Cấp độ", getSeniorityLabel(job.seniority_level))}
        ${salary ? renderSummaryMetric("Lương", salary) : ""}
      </dl>
      ${
        skills.length
          ? `<div class="jd-summary-skills">
              ${skills
                .map((skill) => `<span>${escapeHtml(skill)}</span>`)
                .join("")}
            </div>`
          : ""
      }
    `;
  }

  function renderSummaryMetric(label, value) {
    if (!value) {
      return "";
    }

    return `
      <div>
        <dt>${escapeHtml(label)}</dt>
        <dd>${escapeHtml(value)}</dd>
      </div>
    `;
  }

  function showJobDescriptionEditor() {
    elements.jobDescriptionSummary.hidden = true;
    elements.jobDescriptionInput.hidden = false;
    elements.editJdButton.hidden = true;
    elements.jobDescriptionInput.focus();
  }

  return {
    openJobDetail,
    renderJobCard,
    renderJobDescriptionComposerSummary,
    showJobDescriptionEditor,
  };
}
