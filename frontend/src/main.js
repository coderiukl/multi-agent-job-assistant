import {
  searchJobs,
  sendConversationMessage,
  uploadCv,
} from "./api.js";

import "./styles.css";


const MAX_FILE_SIZE = 10 * 1024 * 1024;

const state = {
  messages: [],

  selectedCvFile: null,
  uploadedCvId: null,
  cvUploadStatus: "idle",
  cvUploadRequestId: 0,

  matchingMode: false,
  jobDescription: "",
  currentMatchingResult: null,

  isSending: false,
  jobs: [],
  currentSearchResult: null,
  lastSearchQuery: "",
  currentSort: "relevance",

  selectedJob: null,
};

const elements = {
  newChatButton: document.querySelector("#new-chat-button"),

  messageList: document.querySelector("#message-list"),
  suggestionList: document.querySelector("#suggestion-list"),
  chatForm: document.querySelector("#chat-form"),
  messageInput: document.querySelector("#message-input"),
  sendButton: document.querySelector("#send-button"),
  toggleJdButton: document.querySelector("#toggle-jd-button"),
  jobDescriptionPanel: document.querySelector(
    "#job-description-panel",
  ),
  jobDescriptionInput: document.querySelector(
    "#job-description-input",
  ),
  jobDescriptionCount: document.querySelector(
    "#job-description-count",
  ),
  clearJdButton: document.querySelector("#clear-jd-button"),

  cvInput: document.querySelector("#cv-input"),
  attachCvButton: document.querySelector("#attach-cv-button"),
  removeCvButton: document.querySelector("#remove-cv-button"),
  selectedCv: document.querySelector("#selected-cv"),
  selectedCvName: document.querySelector("#selected-cv-name"),
  selectedCvStatus: document.querySelector("#selected-cv-status"),
  cvStatusBadge: document.querySelector("#cv-status-badge"),

  globalError: document.querySelector("#global-error"),

  jobResults: document.querySelector("#job-results"),
  resultsSummary: document.querySelector("#results-summary"),
  resultCount: document.querySelector("#result-count"),
  searchStrategy: document.querySelector("#search-strategy"),
  activeFilters: document.querySelector("#active-filters"),
  jobSort: document.querySelector("#job-sort"),
  resultsEyebrow: document.querySelector("#results-eyebrow"),
  resultsTitle: document.querySelector("#results-title"),

  jobDetailOverlay: document.querySelector(
    "#job-detail-overlay",
  ),
  jobDetailDrawer: document.querySelector(
    "#job-detail-drawer",
  ),
  jobDetailContent: document.querySelector(
    "#job-detail-content",
  ),
  closeJobDetailButton: document.querySelector(
    "#close-job-detail",
  ),
};


initializeApplication();


function initializeApplication() {
  bindEvents();

  addMessage({
    role: "assistant",
    text:
      "Xin chào! Mình là CareerPilot. Mình có thể giúp bạn " +
      "tìm việc, phân tích CV và tư vấn định hướng nghề nghiệp.",
  });

  showInitialJobState();
}


function bindEvents() {
  elements.messageInput.addEventListener(
    "input",
    updateSendButton,
  );

  elements.messageInput.addEventListener(
    "keydown",
    (event) => {
      if (
        event.key === "Enter" &&
        !event.shiftKey
      ) {
        event.preventDefault();
        elements.chatForm.requestSubmit();
      }
    },
  );

  elements.chatForm.addEventListener(
    "submit",
    handleSubmit,
  );

  elements.toggleJdButton.addEventListener(
    "click",
    () => setMatchingMode(!state.matchingMode),
  );

  elements.jobDescriptionInput.addEventListener(
    "input",
    handleJobDescriptionInput,
  );

  elements.clearJdButton.addEventListener(
    "click",
    clearJobDescription,
  );

  elements.attachCvButton.addEventListener(
    "click",
    () => {
      elements.cvInput.click();
    },
  );

  elements.cvInput.addEventListener(
    "change",
    handleCvSelection,
  );

  elements.removeCvButton.addEventListener(
    "click",
    removeCv,
  );

  elements.newChatButton.addEventListener(
    "click",
    resetConversation,
  );

  elements.suggestionList.addEventListener(
    "click",
    handleSuggestionClick,
  );

  elements.jobResults.addEventListener(
    "click",
    handleJobResultClick,
  );

  elements.jobSort.addEventListener(
    "change",
    handleSortChange,
  );

  elements.closeJobDetailButton.addEventListener(
    "click",
    closeJobDetail,
  );

  elements.jobDetailOverlay.addEventListener(
    "click",
    closeJobDetail,
  );

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeJobDetail();
    }
  });
}


async function handleSubmit(event) {
  event.preventDefault();

  const typedMessage = elements.messageInput.value.trim();
  const jobDescription = state.matchingMode
    ? elements.jobDescriptionInput.value.trim()
    : null;
  const message = typedMessage || (
    jobDescription
      ? "Hãy đánh giá mức độ phù hợp giữa CV của tôi và công việc này"
      : ""
  );

  if (!message || state.isSending) {
    return;
  }

  if (state.matchingMode && !state.uploadedCvId) {
    showError(
      "Hãy tải lên CV và chờ phân tích thành công trước khi so khớp.",
    );
    return;
  }

  if (state.matchingMode && !jobDescription) {
    showError("Hãy dán Job Description cần so khớp.");
    elements.jobDescriptionInput.focus();
    return;
  }

  if (state.cvUploadStatus === "uploading") {
    showError(
      "CV đang được tải lên và xử lý. " +
      "Vui lòng chờ hoàn tất.",
    );
    return;
  }

  clearError();

  state.isSending = true;

  addMessage({
    role: "user",
    text: message,
  });

  elements.messageInput.value = "";
  elements.suggestionList.hidden = true;

  setComposerDisabled(true);
  showTypingIndicator();

  try {
    const conversation = await sendConversationMessage({
      message,
      cvId: state.uploadedCvId,
      jobDescription,
    });

    removeTypingIndicator();

    addMessage({
      role: "assistant",
      text: conversation.answer,
    });

    if (conversation.route === "job_search") {
      await handleJobSearchConversation(
        message,
        conversation.jobSearchResult,
      );
    }

    if (
      conversation.route === "job_matching" &&
      conversation.jobMatchingResult
    ) {
      renderJobMatchingResult(
        conversation.jobMatchingResult,
      );
    }
  } catch (error) {
    removeTypingIndicator();

    const errorMessage =
      error?.message ||
      "Đã xảy ra lỗi khi xử lý yêu cầu.";

    showError(errorMessage);

    addMessage({
      role: "assistant",
      text:
        "Mình chưa thể xử lý yêu cầu này. " +
        "Bạn hãy kiểm tra backend và thử lại.",
    });
  } finally {
    state.isSending = false;
    setComposerDisabled(false);
    elements.messageInput.focus();
  }
}


async function handleJobSearchConversation(
  query,
  conversationSearchResult,
) {
  state.lastSearchQuery = query;
  state.currentSort = "relevance";
  elements.jobSort.value = "relevance";

  if (conversationSearchResult) {
    renderJobSearchResult(conversationSearchResult);
    return;
  }

  /*
   * Fallback:
   * Nếu Conversation Graph mới chỉ route sang job_search
   * nhưng chưa trả job_search_result, frontend gọi trực tiếp
   * endpoint /jobs/search.
   */

  showJobLoading();

  const searchResult = await searchJobs({
    query,
    sort: state.currentSort,
    page: 1,
    pageSize: 10,
  });

  renderJobSearchResult(searchResult);
}


async function handleSortChange(event) {
  const sort = event.target.value;

  if (
    !state.lastSearchQuery ||
    state.isSending
  ) {
    return;
  }

  state.currentSort = sort;
  state.isSending = true;

  clearError();
  showJobLoading();

  try {
    const result = await searchJobs({
      query: state.lastSearchQuery,
      sort,
      page: 1,
      pageSize: 10,
    });

    renderJobSearchResult(result);
  } catch (error) {
    showError(
      error?.message ||
      "Không thể sắp xếp lại kết quả.",
    );

    showJobErrorState();
  } finally {
    state.isSending = false;
  }
}


async function handleCvSelection(event) {
  const file = event.target.files?.[0];

  if (!file) {
    return;
  }

  const validationError = validateCvFile(file);

  if (validationError) {
    showError(validationError);
    elements.cvInput.value = "";
    return;
  }

  clearError();

  const requestId = state.cvUploadRequestId + 1;

  state.cvUploadRequestId = requestId;
  state.selectedCvFile = file;
  state.uploadedCvId = null;
  state.cvUploadStatus = "uploading";

  renderCvStatus();

  try {
    const result = await uploadCv(file);

    if (state.cvUploadRequestId !== requestId) {
      return;
    }

    if (!result.fileId) {
      throw new Error(
        "Backend không trả về file_id của CV.",
      );
    }

    state.uploadedCvId = result.fileId;
    state.cvUploadStatus = "uploaded";

    renderCvStatus();

    addMessage({
      role: "assistant",
      text:
        `CV “${result.fileName}” đã được tải lên ` +
        "và phân tích thành công.",
    });
  } catch (error) {
    if (state.cvUploadRequestId !== requestId) {
      return;
    }

    state.uploadedCvId = null;
    state.cvUploadStatus = "failed";

    renderCvStatus();

    showError(
      error?.message ||
      "Không thể tải CV lên backend.",
    );
  }
}


function removeCv() {
  state.cvUploadRequestId += 1;
  state.selectedCvFile = null;
  state.uploadedCvId = null;
  state.cvUploadStatus = "idle";

  elements.cvInput.value = "";

  renderCvStatus();
  clearError();
}


function renderCvStatus() {
  const file = state.selectedCvFile;

  if (!file) {
    elements.selectedCv.hidden = true;
    elements.cvStatusBadge.textContent = "Chưa có CV";
    elements.cvStatusBadge.classList.remove("is-ready");
    return;
  }

  elements.selectedCv.hidden = false;
  elements.selectedCvName.textContent = file.name;

  if (state.cvUploadStatus === "uploading") {
    elements.selectedCvStatus.textContent =
      "Đang tải lên và phân tích...";

    elements.cvStatusBadge.textContent =
      "Đang xử lý CV";

    elements.cvStatusBadge.classList.remove("is-ready");
    return;
  }

  if (state.cvUploadStatus === "uploaded") {
    elements.selectedCvStatus.textContent =
      "Đã tải lên và phân tích thành công";

    elements.cvStatusBadge.textContent = "CV sẵn sàng";
    elements.cvStatusBadge.classList.add("is-ready");
    return;
  }

  if (state.cvUploadStatus === "failed") {
    elements.selectedCvStatus.textContent =
      "Tải lên hoặc phân tích thất bại";

    elements.cvStatusBadge.textContent = "CV bị lỗi";
    elements.cvStatusBadge.classList.remove("is-ready");
    return;
  }

  elements.selectedCvStatus.textContent = "Đã chọn CV";
}


function setMatchingMode(enabled, jobDescription = "") {
  state.matchingMode = enabled;

  if (jobDescription) {
    state.jobDescription = jobDescription;
    elements.jobDescriptionInput.value = jobDescription;
  }

  elements.jobDescriptionPanel.hidden = !enabled;
  elements.toggleJdButton.classList.toggle("is-active", enabled);
  elements.toggleJdButton.setAttribute(
    "aria-pressed",
    String(enabled),
  );

  updateJobDescriptionCount();
  updateSendButton();

  if (enabled) {
    elements.jobDescriptionInput.focus();
  }
}


function handleJobDescriptionInput(event) {
  state.jobDescription = event.target.value;
  updateJobDescriptionCount();
  updateSendButton();
}


function clearJobDescription() {
  state.jobDescription = "";
  elements.jobDescriptionInput.value = "";
  updateJobDescriptionCount();
  updateSendButton();
  elements.jobDescriptionInput.focus();
}


function updateJobDescriptionCount() {
  const length = elements.jobDescriptionInput.value.length;
  elements.jobDescriptionCount.textContent =
    `${length.toLocaleString("vi-VN")}/20.000`;
}


function handleSuggestionClick(event) {
  const matchingButton = event.target.closest(
    "[data-action='open-matching']",
  );

  if (matchingButton) {
    setMatchingMode(true);
    elements.messageInput.value =
      "Hãy đánh giá mức độ phù hợp giữa CV của tôi và công việc này";
    updateSendButton();
    return;
  }

  const button = event.target.closest("[data-message]");

  if (!button) {
    return;
  }

  elements.messageInput.value =
    button.dataset.message ?? "";

  elements.messageInput.focus();
  updateSendButton();
}


function handleJobResultClick(event) {
  const matchingButton = event.target.closest(
    "[data-action='match-job']",
  );
  const detailButton = event.target.closest(
    "[data-action='view-job']",
  );

  const actionButton = matchingButton || detailButton;

  if (!actionButton) {
    return;
  }

  const jobId = actionButton.dataset.jobId;

  if (!jobId) {
    return;
  }

  const hit = state.jobs.find(
    (item) => item?.job?.job_id === jobId,
  );

  if (!hit) {
    return;
  }

  if (matchingButton) {
    prepareSelectedJobForMatching(hit);
    return;
  }

  openJobDetail(hit);
}


function prepareSelectedJobForMatching(hit) {
  const job = hit?.job ?? {};
  const description = String(job.description ?? "").trim();

  if (!state.uploadedCvId) {
    showError(
      "Hãy tải lên CV trước khi đánh giá độ phù hợp với công việc.",
    );
    return;
  }

  if (!description) {
    showError("Công việc này chưa có JD để thực hiện so khớp.");
    return;
  }

  clearError();
  setMatchingMode(true, description);
  elements.messageInput.value =
    `Đánh giá CV của tôi với vị trí ${job.title || "này"}`;
  updateSendButton();
  closeJobDetail();
  elements.messageInput.focus();
}


function renderJobSearchResult(result) {
  const items = Array.isArray(result?.items)
    ? result.items
    : [];

  state.currentSearchResult = result;
  state.jobs = items;

  elements.resultsSummary.hidden = false;
  elements.jobSort.disabled = false;

  elements.resultCount.textContent =`Đang hiển thị ${result.items.length} công việc được đề xuất`;

  elements.searchStrategy.textContent = getStrategyLabel(result.strategy);

  renderMatchedTermChips(items);

  if (items.length === 0) {
    showNoJobResults();
    return;
  }

  elements.jobResults.innerHTML = items.map(renderJobCard).join("");
}


function renderJobMatchingResult(result) {
  state.currentMatchingResult = result;
  const score = clampMatchingScore(result?.overallScore);
  const breakdown = result?.breakdown ?? {};
  const strengths = Array.isArray(result?.strengths)
    ? result.strengths
    : [];
  const gaps = Array.isArray(result?.gaps)
    ? result.gaps
    : [];
  const evidence = Array.isArray(result?.evidence)
    ? result.evidence
    : [];

  elements.resultsEyebrow.textContent = "CV · JOB MATCHING";
  elements.resultsTitle.textContent = "Kết quả so khớp";
  elements.resultsSummary.hidden = true;
  elements.jobSort.disabled = true;

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
          <p>${escapeHtml(result?.summary || "Chưa có nhận xét tổng quan.")}</p>

          ${
            result?.confidence === null ||
            result?.confidence === undefined
              ? ""
              : `
                <small>
                  Độ tin cậy đánh giá:
                  ${Math.round(result.confidence * 100)}%
                </small>
              `
          }
        </div>
      </header>

      <section class="matching-section">
        <h3>Điểm thành phần</h3>
        <div class="breakdown-grid">
          ${renderBreakdownItem(
            "Kỹ năng chuyên môn",
            breakdown.technicalSkills,
          )}
          ${renderBreakdownItem(
            "Kinh nghiệm",
            breakdown.experience,
          )}
          ${renderBreakdownItem(
            "Dự án",
            breakdown.projects,
          )}
          ${renderBreakdownItem(
            "Học vấn",
            breakdown.education,
          )}
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


function renderBreakdownItem(label, value) {
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
  const cvEvidence = Array.isArray(item?.cvEvidence)
    ? item.cvEvidence
    : [];

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


function renderMatchedTermChips(items) {
  const matchedTerms = [
    ...new Set(
      items.flatMap((item) =>
        Array.isArray(item.matchedTerms)
          ? item.matchedTerms
          : [],
      ),
    ),
  ].slice(0, 6);

  elements.activeFilters.innerHTML = "";

  for (const term of matchedTerms) {
    const chip = document.createElement("span");

    chip.className = "filter-chip";
    chip.textContent = term;

    elements.activeFilters.append(chip);
  }
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
  const matchPercentage = formatScore(score.final);

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

        <div class="match-score">
          <strong>${matchPercentage}</strong>
          <small>liên quan</small>
        </div>
      </header>

      <div class="job-meta">
        ${renderMetaItem(
          "Địa điểm",
          job.location || "Không xác định",
        )}

        ${renderMetaItem(
          "Cấp độ",
          getSeniorityLabel(job.seniority_level),
        )}

        ${renderMetaItem(
          "Hình thức",
          getWorkModeLabel(job.work_mode),
        )}

        ${renderMetaItem(
          "Loại việc",
          getEmploymentTypeLabel(job.employment_type),
        )}

        ${
          salary
            ? renderMetaItem("Mức lương", salary)
            : ""
        }
      </div>

      ${
        skills.length
          ? `
            <div class="skill-list">
              ${skills
                .map(
                  (skill) => `
                    <span class="skill-chip">
                      ${escapeHtml(skill)}
                    </span>
                  `,
                )
                .join("")}
            </div>
          `
          : ""
      }

      ${
        reasons.length
          ? `
            <ul class="reason-list">
              ${reasons
                .map(
                  (reason) => `
                    <li>${escapeHtml(reason)}</li>
                  `,
                )
                .join("")}
            </ul>
          `
          : ""
      }

      <footer class="job-card-actions">
        <button
          type="button"
          class="ghost-button"
          data-action="view-job"
          data-job-id="${escapeHtml(jobId)}"
        >
          Xem chi tiết
        </button>

        <button
          type="button"
          class="primary-button"
          data-action="match-job"
          data-job-id="${escapeHtml(jobId)}"
        >
          So khớp CV
        </button>

        ${
          sourceUrl
            ? `
              <a
                class="primary-button"
                href="${escapeHtml(sourceUrl)}"
                target="_blank"
                rel="noopener noreferrer"
              >
                Ứng tuyển
              </a>
            `
            : ""
        }
      </footer>
    </article>
  `;
}


function renderMetaItem(label, value) {
  if (!value) {
    return "";
  }

  return `
    <span class="job-meta-item">
      <span class="job-meta-label">
        ${escapeHtml(label)}:
      </span>

      ${escapeHtml(value)}
    </span>
  `;
}


function openJobDetail(hit) {
  const job = hit?.job ?? {};
  const sourceUrl = safeExternalUrl(job.source_url);

  state.selectedJob = hit;

  elements.jobDetailContent.innerHTML = `
    <section class="drawer-job-heading">
      <h2>${escapeHtml(job.title || "Công việc")}</h2>
      <p>${escapeHtml(job.company || "Chưa có công ty")}</p>
    </section>

    <div class="job-meta">
      ${renderMetaItem(
        "Địa điểm",
        job.location || "Không xác định",
      )}

      ${renderMetaItem(
        "Cấp độ",
        getSeniorityLabel(job.seniority_level),
      )}

      ${renderMetaItem(
        "Hình thức",
        getWorkModeLabel(job.work_mode),
      )}

      ${renderMetaItem(
        "Loại việc",
        getEmploymentTypeLabel(job.employment_type),
      )}

      ${renderMetaItem(
        "Ngày đăng",
        formatDate(job.posted_at),
      )}

      ${renderMetaItem(
        "Nguồn",
        job.source || "Không xác định",
      )}
    </div>

    ${
      Array.isArray(job.skills) && job.skills.length
        ? `
          <section class="drawer-section">
            <h3>Kỹ năng</h3>

            <div class="skill-list">
              ${job.skills
                .map(
                  (skill) => `
                    <span class="skill-chip">
                      ${escapeHtml(skill)}
                    </span>
                  `,
                )
                .join("")}
            </div>
          </section>
        `
        : ""
    }

    ${
      Array.isArray(hit.reasons) && hit.reasons.length
        ? `
          <section class="drawer-section">
            <h3>Vì sao công việc này phù hợp?</h3>

            <ul class="reason-list">
              ${hit.reasons
                .map(
                  (reason) => `
                    <li>${escapeHtml(reason)}</li>
                  `,
                )
                .join("")}
            </ul>
          </section>
        `
        : ""
    }

    <section class="drawer-section">
      <h3>Chi tiết JD</h3>

      ${renderJobDescription(job.description)}
    </section>

    <div class="drawer-actions">
      <button
        type="button"
        class="primary-button"
        id="match-drawer-job"
      >
        So khớp với CV
      </button>

      ${
        sourceUrl
          ? `
            <a
              class="primary-button"
              href="${escapeHtml(sourceUrl)}"
              target="_blank"
              rel="noopener noreferrer"
            >
              Đi đến trang ứng tuyển
            </a>
          `
          : ""
      }

      <button
        type="button"
        class="ghost-button"
        id="close-drawer-action"
      >
        Đóng
      </button>
    </div>
  `;

  elements.jobDetailContent
    .querySelector("#match-drawer-job")
    ?.addEventListener(
      "click",
      () => prepareSelectedJobForMatching(hit),
    );

  elements.jobDetailContent
    .querySelector("#close-drawer-action")
    ?.addEventListener(
      "click",
      closeJobDetail,
    );

  elements.jobDetailOverlay.hidden = false;

  elements.jobDetailDrawer.classList.add("is-open");
  elements.jobDetailDrawer.setAttribute(
    "aria-hidden",
    "false",
  );
}


function renderJobDescription(description) {
  const sections = parseJobDescriptionSections(description);

  if (!sections.length) {
    return `
      <p class="job-description-empty">
        Công việc chưa có mô tả chi tiết.
      </p>
    `;
  }

  return `
    <div class="job-description">
      ${sections
        .map(
          (section) => `
            <section class="jd-block">
              <h4>${escapeHtml(section.title)}</h4>

              <ul class="jd-list">
                ${section.items
                  .map(
                    (item) => `
                      <li>${escapeHtml(item)}</li>
                    `,
                  )
                  .join("")}
              </ul>
            </section>
          `,
        )
        .join("")}
    </div>
  `;
}


function parseJobDescriptionSections(description) {
  const lines = String(description ?? "")
    .split(/\r?\n/)
    .map((line) => normalizeDescriptionLine(line))
    .filter(Boolean);

  if (!lines.length) {
    return [];
  }

  const sections = [];
  let currentSection = createDescriptionSection("Thông tin công việc");

  for (const line of lines) {
    const heading = normalizeDescriptionHeading(line);

    if (heading) {
      if (currentSection.items.length) {
        sections.push(currentSection);
      }

      currentSection = createDescriptionSection(heading);
      continue;
    }

    currentSection.items.push(line);
  }

  if (currentSection.items.length) {
    sections.push(currentSection);
  }

  return sections;
}


function createDescriptionSection(title) {
  return {
    title,
    items: [],
  };
}


function normalizeDescriptionLine(line) {
  return String(line ?? "")
    .replace(/^[\s•*+-]+/, "")
    .replace(/^\d+[.)]\s+/, "")
    .trim();
}


function normalizeDescriptionHeading(line) {
  const text = line.replace(/:$/, "").trim();
  const key = text.toLowerCase();

  const headings = {
    "about us": "Giới thiệu công ty",
    "about the company": "Giới thiệu công ty",
    "about the role": "Tổng quan vai trò",
    "the role": "Tổng quan vai trò",
    "job description": "Mô tả công việc",
    "what you will do": "Công việc sẽ làm",
    "your responsibilities": "Trách nhiệm chính",
    responsibilities: "Trách nhiệm chính",
    requirements: "Yêu cầu công việc",
    qualifications: "Yêu cầu công việc",
    "your profile": "Yêu cầu ứng viên",
    "what you bring": "Yêu cầu ứng viên",
    "must have": "Yêu cầu bắt buộc",
    "nice to have": "Điểm cộng",
    "preferred qualifications": "Điểm cộng",
    "tech stack": "Công nghệ sử dụng",
    skills: "Kỹ năng yêu cầu",
    benefits: "Quyền lợi",
    "what we offer": "Quyền lợi",
    "we offer": "Quyền lợi",
    perks: "Quyền lợi",
    "why us?": "Vì sao nên ứng tuyển?",
    "why us": "Vì sao nên ứng tuyển?",
    "why join us?": "Vì sao nên ứng tuyển?",
    "why join us": "Vì sao nên ứng tuyển?",
    "mô tả công việc": "Mô tả công việc",
    "trách nhiệm": "Trách nhiệm chính",
    "yêu cầu": "Yêu cầu công việc",
    "yêu cầu công việc": "Yêu cầu công việc",
    "yêu cầu ứng viên": "Yêu cầu ứng viên",
    "quyền lợi": "Quyền lợi",
    "phúc lợi": "Quyền lợi",
  };

  if (headings[key]) {
    return headings[key];
  }

  if (
    line.endsWith(":") &&
    text.length <= 80 &&
    text.split(/\s+/).length <= 10
  ) {
    return text;
  }

  return null;
}


function closeJobDetail() {
  elements.jobDetailOverlay.hidden = true;

  elements.jobDetailDrawer.classList.remove("is-open");
  elements.jobDetailDrawer.setAttribute(
    "aria-hidden",
    "true",
  );

  state.selectedJob = null;
}


function showJobLoading() {
  elements.resultsSummary.hidden = true;
  elements.jobSort.disabled = true;

  elements.jobResults.innerHTML = `
    <section
      class="job-loading"
      aria-label="Đang tìm công việc"
    >
      <div class="loading-status">
        <span class="loading-spinner"></span>

        <div>
          <strong>Đang tìm công việc phù hợp</strong>
          <small>
            Phân tích yêu cầu và xếp hạng kết quả...
          </small>
        </div>
      </div>

      ${createSkeletonCards(3)}
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


function showInitialJobState() {
  elements.resultsEyebrow.textContent = "JOB DISCOVERY";
  elements.resultsTitle.textContent = "Công việc phù hợp";
  elements.resultsSummary.hidden = true;
  elements.jobSort.disabled = true;
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


function showNoJobResults() {
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


function showJobErrorState() {
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


function resetConversation() {
  state.messages = [];
  state.jobs = [];
  state.currentSearchResult = null;
  state.lastSearchQuery = "";
  state.currentSort = "relevance";
  state.selectedJob = null;
  state.currentMatchingResult = null;
  state.matchingMode = false;
  state.jobDescription = "";
  state.isSending = false;

  elements.messageList.innerHTML = "";
  elements.suggestionList.hidden = false;
  elements.messageInput.value = "";
  elements.jobDescriptionInput.value = "";
  elements.jobSort.value = "relevance";

  setMatchingMode(false);

  clearError();
  closeJobDetail();
  showInitialJobState();
  updateSendButton();

  addMessage({
    role: "assistant",
    text:
      "Cuộc trò chuyện mới đã bắt đầu. " +
      "Bạn muốn tìm công việc hay cần hỗ trợ về CV?",
  });
}


function addMessage({ role, text }) {
  const message = {
    id: crypto.randomUUID(),
    role,
    text,
  };

  state.messages.push(message);

  const article = document.createElement("article");

  article.className =
    `message ${role}-message`;

  if (role === "assistant") {
    const avatar = document.createElement("div");

    avatar.className = "assistant-avatar";
    avatar.textContent = "AI";

    article.append(avatar);
  }

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";

  const paragraph = document.createElement("p");
  paragraph.textContent = text;

  bubble.append(paragraph);
  article.append(bubble);

  elements.messageList.append(article);

  scrollMessagesToBottom();
}


function showTypingIndicator() {
  if (document.querySelector("#typing-indicator")) {
    return;
  }

  const article = document.createElement("article");

  article.id = "typing-indicator";
  article.className =
    "message assistant-message";

  article.innerHTML = `
    <div class="assistant-avatar">AI</div>

    <div
      class="typing-indicator"
      aria-label="CareerPilot đang xử lý"
    >
      <span></span>
      <span></span>
      <span></span>
    </div>
  `;

  elements.messageList.append(article);

  scrollMessagesToBottom();
}


function removeTypingIndicator() {
  document
    .querySelector("#typing-indicator")
    ?.remove();
}


function setComposerDisabled(disabled) {
  elements.messageInput.disabled = disabled;
  elements.attachCvButton.disabled = disabled;
  elements.toggleJdButton.disabled = disabled;
  elements.jobDescriptionInput.disabled = disabled;
  elements.clearJdButton.disabled = disabled;

  elements.sendButton.disabled =
    disabled ||
    !hasComposerContent();
}


function updateSendButton() {
  elements.sendButton.disabled =
    state.isSending ||
    !hasComposerContent();
}


function hasComposerContent() {
  return Boolean(
    elements.messageInput.value.trim() ||
    (
      state.matchingMode &&
      elements.jobDescriptionInput.value.trim()
    ),
  );
}


function showError(message) {
  elements.globalError.textContent = message;
  elements.globalError.hidden = false;
}


function clearError() {
  elements.globalError.textContent = "";
  elements.globalError.hidden = true;
}


function scrollMessagesToBottom() {
  elements.messageList.scrollTo({
    top: elements.messageList.scrollHeight,
    behavior: "smooth",
  });
}


function validateCvFile(file) {
  const isPdf =
    file.type === "application/pdf" ||
    file.name.toLowerCase().endsWith(".pdf");

  if (!isPdf) {
    return "CV phải là tệp PDF.";
  }

  if (file.size > MAX_FILE_SIZE) {
    return "Dung lượng CV không được vượt quá 10 MB.";
  }

  return null;
}


function formatScore(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "0%";
  }

  const normalized = Math.max(
    0,
    Math.min(1, number),
  );

  return `${Math.round(normalized * 100)}%`;
}


function clampMatchingScore(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return 0;
  }

  return Math.max(0, Math.min(100, number));
}


function formatSalary(job) {
  const minimum = toFiniteNumber(job.salary_min);
  const maximum = toFiniteNumber(job.salary_max);

  if (minimum === null && maximum === null) {
    return "";
  }

  const currency = job.salary_currency ?? "";
  const period = getSalaryPeriodLabel(
    job.salary_period,
  );

  if (minimum !== null && maximum !== null) {
    return (
      `${formatMoney(minimum)} – ` +
      `${formatMoney(maximum)} ${currency}${period}`
    );
  }

  if (minimum !== null) {
    return (
      `Từ ${formatMoney(minimum)} ` +
      `${currency}${period}`
    );
  }

  return (
    `Đến ${formatMoney(maximum)} ` +
    `${currency}${period}`
  );
}


function formatMoney(value) {
  return new Intl.NumberFormat("vi-VN", {
    maximumFractionDigits: 0,
  }).format(value);
}


function formatDate(value) {
  if (!value) {
    return "Không xác định";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Không xác định";
  }

  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}


function toFiniteNumber(value) {
  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return null;
  }

  const number = Number(value);

  return Number.isFinite(number)
    ? number
    : null;
}


function getStrategyLabel(strategy) {
  const labels = {
    hybrid: "Tìm kiếm kết hợp PostgreSQL và Qdrant",
    semantic: "Tìm kiếm ngữ nghĩa bằng Qdrant",
    postgres: "Tìm kiếm bằng PostgreSQL",
  };

  return labels[strategy] ?? "Tìm kiếm công việc";
}


function getRecommendationLabel(value) {
  const labels = {
    strong_match: "Rất phù hợp",
    good_match: "Phù hợp",
    partial_match: "Phù hợp một phần",
    low_match: "Mức độ phù hợp thấp",
  };

  return labels[value] ?? "Chưa xác định";
}


function getEvidenceStatusLabel(value) {
  const labels = {
    matched: "Đáp ứng",
    partial: "Một phần",
    missing: "Còn thiếu",
    not_applicable: "Không áp dụng",
  };

  return labels[value] ?? "Chưa xác định";
}


function getSeniorityLabel(value) {
  const labels = {
    intern: "Thực tập",
    fresher: "Fresher",
    junior: "Junior",
    middle: "Middle",
    senior: "Senior",
    lead: "Lead",
    manager: "Quản lý",
    director: "Giám đốc",
    unknown: "Không xác định",
  };

  return labels[value] ?? "Không xác định";
}


function getWorkModeLabel(value) {
  const labels = {
    onsite: "Tại văn phòng",
    remote: "Từ xa",
    hybrid: "Kết hợp",
    unknown: "Không xác định",
  };

  return labels[value] ?? "Không xác định";
}


function getEmploymentTypeLabel(value) {
  const labels = {
    full_time: "Toàn thời gian",
    part_time: "Bán thời gian",
    contract: "Hợp đồng",
    internship: "Thực tập",
    freelance: "Freelance",
    temporary: "Tạm thời",
    other: "Khác",
  };

  return labels[value] ?? "Không xác định";
}


function getSalaryPeriodLabel(value) {
  const labels = {
    hourly: "/giờ",
    weekly: "/tuần",
    fortnightly: "/2 tuần",
    monthly: "/tháng",
    annual: "/năm",
  };

  return labels[value] ?? "";
}


function safeExternalUrl(value) {
  if (!value) {
    return null;
  }

  try {
    const url = new URL(value);

    if (
      url.protocol !== "http:" &&
      url.protocol !== "https:"
    ) {
      return null;
    }

    return url.toString();
  } catch {
    return null;
  }
}


function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
