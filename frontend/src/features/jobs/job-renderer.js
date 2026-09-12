import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import {
  formatDate,
  formatSalary,
  formatScore,
} from "../../shared/formatters.js";
import { escapeHtml, safeExternalUrl } from "../../shared/html.js";
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
  function renderMetaItem(label, value) {
    if (!value) {
      return "";
    }

    const salaryClass = label === "Lương" ? "is-salary" : "";

    return `
      <span class="job-meta-item ${salaryClass}">
        <span class="job-meta-label">${escapeHtml(label)}:</span>
        ${escapeHtml(value)}
      </span>
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
      "is-strong": "rất khớp",
      "is-good": "đáng xem",
      "is-low": "cần lọc",
    };

    return labels[getMatchTone(value)];
  }

  function renderJobCard(hit) {
    const job = hit?.job ?? {};
    const score = hit?.score ?? {};
    const reasons = Array.isArray(hit?.reasons)
      ? hit.reasons.slice(0, 3)
      : [];
    const skills = Array.isArray(job.skills)
      ? job.skills.slice(0, 7)
      : [];
    const jobId = String(job.job_id ?? "");
    const sourceUrl = safeExternalUrl(job.source_url);
    const salary = formatSalary(job);

    return `
      <article class="job-card">
        <header class="job-card-header">
          <div class="job-heading">
            <h3 class="job-title">
              ${escapeHtml(job.title || "Chưa có chức danh")}
            </h3>
            <span class="job-company">
              ${escapeHtml(job.company || "Chưa có công ty")}
            </span>
          </div>
          <div class="match-score ${getMatchTone(score.final)}">
            <strong>${formatScore(score.final)}</strong>
            <small>${escapeHtml(getMatchLabel(score.final))}</small>
          </div>
        </header>

        <div class="job-meta job-meta-priority">
          ${salary ? renderMetaItem("Lương", salary) : ""}
          ${renderMetaItem("Địa điểm", job.location || "Không xác định")}
          ${renderMetaItem("Cấp độ", getSeniorityLabel(job.seniority_level))}
          ${renderMetaItem("Hình thức", getWorkModeLabel(job.work_mode))}
          ${renderMetaItem(
            "Loại việc",
            getEmploymentTypeLabel(job.employment_type),
          )}
        </div>

        ${
          skills.length
            ? `<div class="skill-list">
                ${skills
                  .map(
                    (skill) =>
                      `<span class="skill-chip">${escapeHtml(skill)}</span>`,
                  )
                  .join("")}
              </div>`
            : ""
        }

        ${
          reasons.length
            ? `<div class="reason-block">
                <strong>Vì sao nên xem?</strong>
                <ul class="reason-list">
                  ${reasons
                    .map((reason) => `<li>${escapeHtml(reason)}</li>`)
                    .join("")}
                </ul>
              </div>`
            : ""
        }

        <footer class="job-card-actions">
          <button type="button" class="ghost-button"
            data-action="view-job" data-job-id="${escapeHtml(jobId)}">
            Xem chi tiết
          </button>
          <button type="button" class="primary-button"
            data-action="match-job" data-job-id="${escapeHtml(jobId)}">
            So khớp CV
          </button>
          ${
            sourceUrl
              ? `<a class="primary-button" href="${escapeHtml(sourceUrl)}"
                    target="_blank" rel="noopener noreferrer">Ứng tuyển</a>`
              : ""
          }
          <button type="button" class="ghost-button"
            data-action="cover-letter-job" data-job-id="${escapeHtml(jobId)}">
            Viết thư
          </button>
        </footer>
      </article>
    `;
  }

  function openJobDetail(hit) {
    const job = hit?.job ?? {};
    const sourceUrl = safeExternalUrl(job.source_url);

    state.selectedJob = hit;
    state.lastFocusedBeforeDrawer = document.activeElement;
    elements.jobDetailContent.innerHTML = `
      <section class="drawer-job-heading">
        <h2>${escapeHtml(job.title || "Công việc")}</h2>
        <p>${escapeHtml(job.company || "Chưa có công ty")}</p>
      </section>

      <div class="job-meta">
        ${renderMetaItem("Địa điểm", job.location || "Không xác định")}
        ${renderMetaItem("Cấp độ", getSeniorityLabel(job.seniority_level))}
        ${renderMetaItem("Hình thức", getWorkModeLabel(job.work_mode))}
        ${renderMetaItem(
          "Loại việc",
          getEmploymentTypeLabel(job.employment_type),
        )}
        ${renderMetaItem("Ngày đăng", formatDate(job.posted_at))}
        ${renderMetaItem("Nguồn", job.source || "Không xác định")}
      </div>

      ${
        Array.isArray(job.skills) && job.skills.length
          ? `<section class="drawer-section">
              <h3>Kỹ năng</h3>
              <div class="skill-list">
                ${job.skills
                  .map(
                    (skill) =>
                      `<span class="skill-chip">${escapeHtml(skill)}</span>`,
                  )
                  .join("")}
              </div>
            </section>`
          : ""
      }

      ${
        Array.isArray(hit?.reasons) && hit.reasons.length
          ? `<section class="drawer-section">
              <h3>Vì sao công việc này phù hợp?</h3>
              <ul class="reason-list">
                ${hit.reasons
                  .map((reason) => `<li>${escapeHtml(reason)}</li>`)
                  .join("")}
              </ul>
            </section>`
          : ""
      }

      <section class="drawer-section">
        <h3>Chi tiết JD</h3>
        ${renderJobDescription(job.description)}
      </section>

      <div class="drawer-actions">
        <button type="button" class="primary-button" id="match-drawer-job">
          So khớp với CV
        </button>
        ${
          sourceUrl
            ? `<a class="primary-button" href="${escapeHtml(sourceUrl)}"
                  target="_blank" rel="noopener noreferrer">
                Đi đến trang ứng tuyển
              </a>`
            : ""
        }
        <button type="button" class="ghost-button" id="close-drawer-action">
          Đóng
        </button>
        <button type="button" class="ghost-button" id="cover-letter-drawer-job">
          Viết thư ứng tuyển
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
