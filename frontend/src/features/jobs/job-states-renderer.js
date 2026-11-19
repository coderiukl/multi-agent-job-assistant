import { elements } from "../../core/elements.js";
import { icon } from "../../shared/icons.js";

export function renderJobLoading() {
  if (elements.jobPagination) elements.jobPagination.hidden = true;
  elements.resultsSummary.hidden = true;
  elements.jobSort.disabled = true;
  elements.jobResults.innerHTML = `
    <section class="job-loading" aria-busy="true" aria-live="polite">
      <div class="loading-status" role="status">
        <span class="spinner" aria-hidden="true"></span>
        <div>
          <strong>Đang tìm công việc phù hợp</strong>
          <small>Job Search Agent đang lọc và xếp hạng kết quả</small>
        </div>
      </div>
      ${createSkeletonCards(4)}
    </section>
  `;
}

export function renderInitialJobState() {
  if (elements.jobPagination) elements.jobPagination.hidden = true;
  elements.resultsEyebrow.textContent = "JOB DISCOVERY";
  elements.resultsTitle.textContent = "Công việc phù hợp";
  elements.resultsSummary.hidden = true;
  elements.jobSort.disabled = true;
  elements.backToJobsButton.hidden = true;
  elements.activeFilters.innerHTML = "";
  elements.jobResults.innerHTML = `
    <section class="empty-state">
      <span class="empty-state-icon">${icon("search")}</span>
      <h3>Bắt đầu tìm công việc</h3>
      <p>
        Mô tả vị trí, địa điểm, kỹ năng hoặc cấp độ kinh nghiệm bạn mong muốn
        trong khung trò chuyện. Kết quả sẽ xuất hiện tại đây.
      </p>
    </section>
  `;
}

export function renderNoJobResults() {
  if (elements.jobPagination) elements.jobPagination.hidden = true;
  elements.jobResults.innerHTML = `
    <section class="empty-state">
      <span class="empty-state-icon">${icon("search")}</span>
      <h3>Chưa tìm thấy công việc phù hợp</h3>
      <p>
        Thử mở rộng địa điểm, kỹ năng, cấp độ kinh nghiệm
        hoặc hình thức làm việc trong yêu cầu tiếp theo.
      </p>
    </section>
  `;
}

export function renderJobErrorState() {
  if (elements.jobPagination) elements.jobPagination.hidden = true;
  elements.resultsSummary.hidden = true;
  elements.jobSort.disabled = true;
  elements.jobResults.innerHTML = `
    <section class="empty-state" role="alert">
      <span class="empty-state-icon is-danger">${icon("alert")}</span>
      <h3>Không thể tải kết quả</h3>
      <p>
        Dịch vụ tìm kiếm chưa phản hồi. Hãy kiểm tra kết nối
        và thử tìm kiếm lại sau ít phút.
      </p>
    </section>
  `;
}

function createSkeletonCards(count) {
  return Array.from(
    { length: count },
    () => `
      <div class="skeleton-card" aria-hidden="true">
        <div class="skeleton skeleton-title"></div>
        <div class="skeleton skeleton-company"></div>
        <div class="skeleton skeleton-row"></div>
        <div class="skeleton skeleton-row short"></div>
      </div>
    `,
  ).join("");
}
