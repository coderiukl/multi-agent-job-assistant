import { elements } from "../../core/elements.js";

export function renderJobLoading() {
  elements.resultsSummary.hidden = true;
  elements.jobSort.disabled = true;
  elements.jobResults.innerHTML = `
    <section class="job-loading" aria-label="Đang tìm công việc">
      <div class="loading-status">
        <span class="loading-spinner"></span>
        <div>
          <strong>Đang tìm công việc phù hợp</strong>
          <small>Phân tích yêu cầu và xếp hạng kết quả...</small>
        </div>
      </div>
      ${createSkeletonCards(3)}
    </section>
  `;
}

export function renderInitialJobState() {
  elements.resultsEyebrow.textContent = "JOB DISCOVERY";
  elements.resultsTitle.textContent = "Công việc phù hợp";
  elements.resultsSummary.hidden = true;
  elements.jobSort.disabled = true;
  elements.backToJobsButton.hidden = true;
  elements.activeFilters.innerHTML = "";
  elements.jobResults.innerHTML = `
    <section class="empty-state">
      <div class="empty-illustration">⌕</div>
      <h3>Bắt đầu tìm công việc</h3>
      <p>
        Hãy mô tả vị trí, địa điểm, kỹ năng hoặc
        cấp độ kinh nghiệm bạn mong muốn.
      </p>
      <div class="example-query">
        “Tìm công việc AI tại Hồ Chí Minh phù hợp
        với sinh viên mới ra trường.”
      </div>
    </section>
  `;
}

export function renderNoJobResults() {
  elements.jobResults.innerHTML = `
    <section class="empty-state">
      <div class="empty-illustration">0</div>
      <h3>Chưa tìm thấy công việc phù hợp</h3>
      <p>
        Bạn có thể thử mở rộng địa điểm, kỹ năng,
        cấp độ kinh nghiệm hoặc hình thức làm việc.
      </p>
    </section>
  `;
}

export function renderJobErrorState() {
  elements.resultsSummary.hidden = true;
  elements.jobSort.disabled = true;
  elements.jobResults.innerHTML = `
    <section class="empty-state">
      <div class="empty-illustration">!</div>
      <h3>Không thể tải kết quả</h3>
      <p>
        Hãy kiểm tra FastAPI, PostgreSQL và Qdrant,
        sau đó thử tìm kiếm lại.
      </p>
    </section>
  `;
}

function createSkeletonCards(count) {
  return Array.from(
    { length: count },
    () => `
      <article class="job-card skeleton-card">
        <div class="skeleton skeleton-title"></div>
        <div class="skeleton skeleton-company"></div>
        <div class="skeleton skeleton-row"></div>
        <div class="skeleton skeleton-row short"></div>
      </article>
    `,
  ).join("");
}
