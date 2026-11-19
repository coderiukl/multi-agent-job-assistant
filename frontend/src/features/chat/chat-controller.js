import { sendConversationMessage } from "../../api.js";
import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import {
  normalizeHumanReview,
  resumeConversation,
} from "../../api/conversation-api.js";
import { createIcon } from "../../shared/icons.js";
import { summarizeTurnForMessage } from "./chat-renderer.js";

const REVIEW_COPY = {
  cover_letter_confirmation: {
    title: "Xác nhận thông tin trước khi viết thư",
    description:
      "Kiểm tra công việc mục tiêu và nội dung JD. Bạn có thể chỉnh sửa trước khi tạo bản nháp.",
    approve: "Tạo bản nháp",
  },
  cover_letter_draft: {
    title: "Duyệt bản nháp thư ứng tuyển",
    description:
      "Đọc và chỉnh sửa trực tiếp nội dung. Bản đã duyệt sẽ được dùng làm thư hoàn chỉnh.",
    approve: "Duyệt bản nháp",
  },
};

export function createChatController({
  addMessage,
  cacheConversation,
  clearError,
  clearComposerContextAfterSubmit,
  closeJobDetail,
  handleJobSearchConversation,
  rememberConversationThread,
  rememberConversationResults,
  removeTypingIndicator,
  renderCareerAdviceResult,
  renderCoverLetterResult,
  renderCvAnalysisResult,
  renderJobMatchingResult,
  renderWorkflowJobRecommendations,
  resizeMessageInput,
  saveThreadId,
  setComposerDisabled,
  showError,
  showTypingIndicator,
  updateComposerContext,
}) {
  function readComposerInput() {
    const typedMessage = elements.messageInput.value.trim();
    const jobDescription = state.matchingMode
      ? elements.jobDescriptionInput.value.trim()
      : null;
    const defaultMatchingMessage =
      "Hãy đánh giá mức độ phù hợp giữa CV của tôi và công việc này";
    const defaultCvMessage =
      "Hãy phân tích CV của tôi và đề xuất các điểm cần cải thiện";

    return {
      message:
        typedMessage ||
        (jobDescription ? defaultMatchingMessage : "") ||
        (
          state.selectedCvFile && state.cvUploadStatus === "uploaded"
            ? defaultCvMessage
            : ""
        ),
      jobDescription,
    };
  }

  function validateComposerInput({ message, jobDescription }) {
    if (state.matchingMode && !state.uploadedCvId) {
      return (
        "Hãy tải lên CV và chờ phân tích thành công " +
        "trước khi thực hiện yêu cầu với JD."
      );
    }

    if (state.matchingMode && !jobDescription) {
      return "Hãy dán Job Description cần so khớp.";
    }

    if (state.cvUploadStatus === "uploading") {
      return "CV đang được tải lên và xử lý. Vui lòng chờ hoàn tất.";
    }

    if (state.cvUploadStatus === "failed") {
      return "CV xử lý thất bại. Hãy xóa CV lỗi và tải lại.";
    }

    return null;
  }

  function canSubmitComposer(input) {
    return Boolean(input.message) && !state.isSending;
  }

  function clearComposerAfterSubmit() {
    elements.messageInput.value = "";
    elements.suggestionList.hidden = true;
    clearComposerContextAfterSubmit();

    resizeMessageInput();
    updateComposerContext();
  }

  async function handleJobSearchRoute(conversation, originalMessage) {
    if (conversation.workflowJobMatches.length) {
      renderWorkflowJobRecommendations(
        conversation.jobSearchResult,
        conversation.workflowJobMatches,
        conversation.careerAdviceResult,
        {
          matchingExecution: conversation.matchingExecution,
          outcomes: conversation.workflowJobMatchOutcomes,
        },
      );
      return;
    }

    await handleJobSearchConversation(
      originalMessage,
      conversation.jobSearchResult,
      conversation.searchContext,
    );
  }

  async function handleConversationResult(conversation, originalMessage) {
    rememberConversationResults(conversation, originalMessage);

    state.currentWorkflow = conversation.workflow;
    state.workflowJobMatches = conversation.workflowJobMatches;

    const handlers = {
      job_search: () =>
        handleJobSearchRoute(conversation, originalMessage),
      cv_analysis: () =>
        conversation.cvAnalysisResult &&
        renderCvAnalysisResult(conversation.cvAnalysisResult),
      cover_letter: () =>
        conversation.coverLetterResult &&
        renderCoverLetterResult(conversation.coverLetterResult),
      career_advice: () =>
        conversation.careerAdviceResult &&
        renderCareerAdviceResult(conversation.careerAdviceResult),
      job_matching: () =>
        conversation.jobMatchingResult &&
        renderJobMatchingResult(conversation.jobMatchingResult),
    };

    await handlers[conversation.route]?.();
  }

  function handleConversationError(error, rejectedMessage = "") {
    if (restorePendingReviewFromError(error, rejectedMessage)) {
      return;
    }

    const restored = restoreComposerText(rejectedMessage);

    showError(
      (error?.message || "Đã xảy ra lỗi khi xử lý yêu cầu.") +
        (restored
          ? " Nội dung đã được đặt lại trong ô nhập để bạn gửi lại."
          : ""),
    );

    addMessage({
      role: "assistant",
      text:
        "Mình chưa thể xử lý yêu cầu này lúc này. " +
        "Bạn có thể thử gửi lại sau ít phút.",
    });
  }

  function restoreComposerText(text) {
    if (!text || elements.messageInput.value.trim()) {
      return false;
    }

    elements.messageInput.value = text;
    resizeMessageInput();
    return true;
  }

  function renderHumanReviewActions() {
    const existingContainer = elements.messageList.querySelector(
      ".human-review-actions",
    );

    if (existingContainer) {
      existingContainer.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
      return;
    }

    const review = state.pendingHumanReview;
    const copy = REVIEW_COPY[review.reviewType] ?? {
      title: "Cần bạn xác nhận",
      description: review.message,
      approve: "Tiếp tục",
    };
    const titleId = `review-title-${review.reviewId ?? "pending"}`;

    const container = document.createElement("section");
    container.className = "human-review-actions";
    container.setAttribute("aria-labelledby", titleId);

    const header = document.createElement("header");
    const iconWrap = document.createElement("span");
    const heading = document.createElement("div");
    const eyebrow = document.createElement("p");
    const title = document.createElement("h3");
    const description = document.createElement("p");

    header.className = "review-card-header";
    iconWrap.className = "review-card-icon";
    iconWrap.append(createIcon("flag"));
    eyebrow.className = "eyebrow";
    eyebrow.textContent = "Cần bạn xác nhận";
    title.id = titleId;
    title.textContent = copy.title;
    description.textContent = copy.description;
    heading.append(eyebrow, title, description);
    header.append(iconWrap, heading);
    container.append(header);

    const body = document.createElement("div");
    body.className = "human-review-body";

    if (review.reviewType === "cover_letter_confirmation") {
      renderCoverLetterInputReview(body, review);
    } else if (review.reviewType === "cover_letter_draft") {
      renderCoverLetterDraftReview(body, review);
    }

    // `feedback` is only read by the backend when the review is rejected.
    const feedback = document.createElement("details");
    const feedbackSummary = document.createElement("summary");
    feedback.className = "human-review-feedback";
    feedbackSummary.textContent = "Dừng kèm lý do (tùy chọn)";
    feedback.append(feedbackSummary);
    appendReviewField(feedback, {
      label: "Lý do được gửi kèm khi bạn chọn “Dừng tạo thư”",
      name: "feedback",
      multiline: true,
    });
    body.append(feedback);
    container.append(body);

    const buttonRow = document.createElement("footer");
    buttonRow.className = "human-review-buttons";

    const status = document.createElement("span");
    status.className = "human-review-status";
    status.setAttribute("role", "status");

    const rejectButton = document.createElement("button");
    rejectButton.type = "button";
    rejectButton.className = "btn btn-ghost human-review-reject";
    rejectButton.textContent = "Dừng tạo thư";

    const approveButton = document.createElement("button");
    approveButton.type = "button";
    approveButton.className = "btn btn-primary human-review-approve";
    approveButton.textContent = copy.approve;

    buttonRow.append(status, rejectButton, approveButton);
    container.append(buttonRow);

    approveButton.addEventListener("click", () => {
      handleHumanReviewDecision("approve", container);
    });

    rejectButton.addEventListener("click", () => {
      handleHumanReviewDecision("reject", container);
    });

    elements.messageList.append(container);

    container.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
    });
  }

  function appendReviewField(
    container,
    { label, value = "", name, multiline = false },
  ) {
    const wrapper = document.createElement("label");
    wrapper.className = "human-review-field";
    const caption = document.createElement("span");
    caption.textContent = label;
    const control = document.createElement(multiline ? "textarea" : "input");
    if (!multiline) control.type = "text";
    control.dataset.reviewField = name;
    control.value = value ?? "";
    if (multiline) control.rows = name === "editedDraft" ? 14 : 5;
    wrapper.append(caption, control);
    container.append(wrapper);
    return control;
  }

  function renderCoverLetterInputReview(container, review) {
    const jobs = Array.isArray(review.data?.jobs) ? review.data.jobs : [];
    const cvMeta = document.createElement("p");
    cvMeta.className = "human-review-meta";
    cvMeta.textContent = [
      `CV: ${review.data?.cv_name || review.data?.cv_id || "không xác định"}`,
      review.data?.cv_version ? `phiên bản ${review.data.cv_version}` : null,
    ].filter(Boolean).join(" · ");
    container.append(cvMeta);

    const selectLabel = document.createElement("label");
    selectLabel.className = "human-review-field";
    selectLabel.hidden = jobs.length === 0;
    const caption = document.createElement("span");
    caption.textContent = "Công việc mục tiêu";
    const select = document.createElement("select");
    select.dataset.reviewField = "selectedJobId";

    jobs.forEach((job, index) => {
      const option = document.createElement("option");
      option.value = job.job_id;
      const score = typeof job.match_score === "number"
        ? ` · ${job.match_score.toFixed(1)}/100`
        : "";
      option.textContent = `${job.title || "Chưa có chức danh"} · ${job.company || "Chưa có công ty"}${score}`;
      option.selected = (
        job.job_id === review.data?.selected_job_id || index === 0
      );
      select.append(option);
    });
    selectLabel.append(caption, select);
    container.append(selectLabel);

    const jobMeta = document.createElement("p");
    jobMeta.className = "human-review-meta";
    container.append(jobMeta);

    const selectedJob = () => (
      jobs.find((job) => job.job_id === select.value) ?? jobs[0] ?? {}
    );
    const updateJobMeta = () => {
      const job = selectedJob();
      jobMeta.textContent = [
        `Job ID: ${job.job_id || "không xác định"}`,
        job.jd_version ? `JD phiên bản ${job.jd_version}` : null,
      ].filter(Boolean).join(" · ");
    };
    const identityGrid = document.createElement("div");
    identityGrid.className = "human-review-grid";
    container.append(identityGrid);

    const title = appendReviewField(identityGrid, {
      label: "Chức danh",
      name: "jobTitle",
      value: selectedJob().title,
    });
    const company = appendReviewField(identityGrid, {
      label: "Công ty",
      name: "company",
      value: selectedJob().company,
    });
    const description = appendReviewField(container, {
      label: "Mô tả công việc",
      name: "jobDescription",
      value: selectedJob().description,
      multiline: true,
    });
    const instructions = appendReviewField(container, {
      label: "Yêu cầu thêm cho thư (tùy chọn)",
      name: "instructions",
      multiline: true,
    });
    instructions.placeholder =
      "Ví dụ: nhấn mạnh kinh nghiệm dự án dữ liệu, giọng văn ngắn gọn…";

    select.addEventListener("change", () => {
      const job = selectedJob();
      title.value = job.title ?? "";
      company.value = job.company ?? "";
      description.value = job.description ?? "";
      updateJobMeta();
    });
    updateJobMeta();
  }

  function renderCoverLetterDraftReview(container, review) {
    appendReviewField(container, {
      label: "Nội dung bản nháp",
      name: "editedDraft",
      value: review.data?.draft,
      multiline: true,
    });
  }

  function restorePendingReviewFromError(error, rejectedMessage = "") {
    const errorPayload = error?.details?.error;

    if (
      error?.status !== 409 ||
      errorPayload?.code !== "HUMAN_REVIEW_PENDING"
    ) {
      return false;
    }

    const review = normalizeHumanReview(
      errorPayload?.details?.pending_human_review,
    );

    if (!review) {
      return false;
    }

    rollbackRejectedMessage(rejectedMessage);

    state.pendingHumanReview = review;

    const reviewMessageAlreadyExists = state.messages.some(
      (message) => (
        message.role === "assistant" &&
        message.text === review.message
      ),
    );

    if (!reviewMessageAlreadyExists) {
      addMessage({
        role: "assistant",
        text: review.message,
      });
    } else {
      cacheConversation();
    }

    renderHumanReviewActions();
    showError(errorPayload.message);
    return true;
  }

  function rollbackRejectedMessage(rejectedMessage) {
    const lastMessage = state.messages.at(-1);

    if (
      lastMessage?.role === "user" &&
      (!rejectedMessage || lastMessage.text === rejectedMessage)
    ) {
      state.messages.pop();
      const userMessages = elements.messageList.querySelectorAll(
        ".user-message",
      );
      userMessages.item(userMessages.length - 1)?.remove();
    }

    if (rejectedMessage) {
      elements.messageInput.value = rejectedMessage;
      resizeMessageInput();
    }
  }

  async function handleHumanReviewDecision(action, container) {
    if (!state.pendingHumanReview) {
      return;
    }

    const buttons = container.querySelectorAll("button");
    const status = container.querySelector(".human-review-status");
    const actionButton = container.querySelector(
      action === "approve" ? ".human-review-approve" : ".human-review-reject",
    );

    const setBusy = (busy) => {
      buttons.forEach((button) => {
        button.disabled = busy;
      });
      container.setAttribute("aria-busy", String(busy));

      if (busy) {
        actionButton?.setAttribute("aria-busy", "true");
      } else {
        actionButton?.removeAttribute("aria-busy");
      }

      if (!status) {
        return;
      }

      status.replaceChildren();
      status.classList.toggle("is-busy", busy);

      if (busy) {
        const spinner = document.createElement("span");
        spinner.className = "spinner";
        spinner.setAttribute("aria-hidden", "true");
        status.append(
          spinner,
          document.createTextNode(
            action === "approve"
              ? "Đang tiếp tục quy trình…"
              : "Đang dừng quy trình…",
          ),
        );
      }
    };

    setBusy(true);

    try {
      const review = state.pendingHumanReview;
      const fieldValue = (name) => (
        container
          .querySelector(`[data-review-field="${name}"]`)
          ?.value?.trim() || null
      );
      const inputOverrides = review.reviewType === "cover_letter_confirmation"
        ? Object.fromEntries(
            Object.entries({
              job_title: fieldValue("jobTitle"),
              company: fieldValue("company"),
              job_description: fieldValue("jobDescription"),
              instructions: fieldValue("instructions"),
            }).filter(([, value]) => value !== null),
          )
        : {};

      const result = await resumeConversation({
        threadId: state.threadId,
        reviewId: review.reviewId,
        action,
        feedback: action === "reject" ? fieldValue("feedback") : null,
        selectedJobId: fieldValue("selectedJobId"),
        inputOverrides,
        editedDraft: fieldValue("editedDraft"),
      });

      state.pendingHumanReview = null;
      cacheConversation();

      container.remove();

      if (
        result.status === "waiting_for_human" &&
        result.humanReview
      ) {
        state.pendingHumanReview = result.humanReview;
        addMessage({
          role: "assistant",
          text: result.humanReview.message,
          result: summarizeTurnForMessage(result),
        });
        renderHumanReviewActions();
        return;
      }

      addMessage({
        role: "assistant",
        text: result.answer,
        result: summarizeTurnForMessage(result),
      });

      await handleConversationResult(result, "");
    } catch (error) {
      const errorCode = error?.details?.error?.code;

      if (
        error?.status === 409 &&
        errorCode === "HUMAN_REVIEW_NOT_PENDING"
      ) {
        state.pendingHumanReview = null;
        container.remove();
        cacheConversation();
      }

      setBusy(false);

      showError(
        error.message || "Không thể tiếp tục xử lý yêu cầu."
      );
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();

    const input = readComposerInput();

    if (!canSubmitComposer(input)) {
      return;
    }

    if (state.pendingHumanReview) {
      showError(
        "Hãy xử lý yêu cầu duyệt hiện tại trước khi gửi tin nhắn mới.",
      );
      renderHumanReviewActions();
      return;
    }

    const validationError = validateComposerInput(input);

    if (validationError) {
      showError(validationError);

      if (state.matchingMode && !input.jobDescription) {
        elements.jobDescriptionInput.focus();
      }
      return;
    }

    clearError();
    state.isSending = true;

    const messageContext = {
      cvId: state.uploadedCvId,
      cvName: state.uploadedCvId
        ? state.uploadedCvName ?? state.selectedCvFile?.name ?? null
        : null,
      jobDescription: input.jobDescription,
    };

    addMessage({
      role: "user",
      text: input.message,
      context: messageContext,
    });
    rememberConversationThread({
      threadId: state.threadId,
      firstMessage: input.message,
      context: messageContext,
    });

    clearComposerAfterSubmit();
    setComposerDisabled(true);
    showTypingIndicator();

    try {
      const conversation = await sendConversationMessage({
        threadId: state.threadId,
        message: input.message,
        cvId: messageContext.cvId,
        cvName: messageContext.cvName,
        jobDescription: input.jobDescription,
      });

      if (conversation.threadId) {
        saveThreadId(conversation.threadId);
      }

      if (
        conversation.status === "waiting_for_human" &&
        conversation.humanReview
      ) {
        state.pendingHumanReview = conversation.humanReview;

        addMessage({
          role: "assistant",
          text: conversation.humanReview.message,
          result: summarizeTurnForMessage(conversation),
        });

        renderHumanReviewActions();
        cacheConversation();
        return;
      }

      addMessage({
        role: "assistant",
        text: conversation.answer,
        result: summarizeTurnForMessage(conversation),
      });

      await handleConversationResult(conversation, input.message);
    } catch (error) {
      handleConversationError(error, input.message);
    } finally {
      removeTypingIndicator();
      state.isSending = false;
      setComposerDisabled(false);
      updateComposerContext();
      elements.messageInput.focus();
    }
  }

  async function runJobConversation({
    hit,
    message,
    getResult,
    renderResult,
    missingDescriptionMessage,
    requestErrorMessage,
    assistantErrorMessage,
  }) {
    const job = hit?.job ?? {};
    const description = String(job.description ?? "").trim();

    if (!state.uploadedCvId) {
      showError("Hãy tải lên CV trước khi thực hiện yêu cầu này.");
      return;
    }

    if (!description) {
      showError(missingDescriptionMessage);
      return;
    }

    if (state.isSending) {
      return;
    }

    if (state.pendingHumanReview) {
      showError(
        "Hãy xử lý yêu cầu duyệt hiện tại trước khi thực hiện tác vụ mới.",
      );
      renderHumanReviewActions();
      return;
    }

    clearError();
    closeJobDetail();
    state.isSending = true;

    const messageContext = {
      cvId: state.uploadedCvId,
      cvName:
        state.uploadedCvName ??
        state.selectedCvFile?.name ??
        null,
      jobDescription: description,
    };

    addMessage({
      role: "user",
      text: message,
      context: messageContext,
    });
    rememberConversationThread({
      threadId: state.threadId,
      firstMessage: message,
      context: messageContext,
    });
    elements.suggestionList.hidden = true;

    setComposerDisabled(true);
    showTypingIndicator();

    try {
      const conversation = await sendConversationMessage({
        threadId: state.threadId,
        message,
        cvId: state.uploadedCvId,
        cvName: messageContext.cvName,
        jobDescription: description,
      });

      if (conversation.threadId) {
        saveThreadId(conversation.threadId);
      }

      if (
        conversation.status === "waiting_for_human" &&
        conversation.humanReview
      ) {
        state.pendingHumanReview = conversation.humanReview;

        addMessage({
          role: "assistant",
          text: conversation.humanReview.message,
          result: summarizeTurnForMessage(conversation),
        });

        renderHumanReviewActions();
        cacheConversation();
        return;
      }

      rememberConversationResults(conversation, message);

      addMessage({
        role: "assistant",
        text: conversation.answer,
        result: summarizeTurnForMessage(conversation),
      });

      const result = getResult(conversation);

      if (result) {
        renderResult(result);
      }
    } catch (error) {
      if (restorePendingReviewFromError(error, message)) {
        return;
      }

      showError(error?.message || requestErrorMessage);
      addMessage({
        role: "assistant",
        text: assistantErrorMessage,
      });
    } finally {
      removeTypingIndicator();
      state.isSending = false;
      setComposerDisabled(false);
      updateComposerContext();
    }
  }

  return {
    handleSubmit,
    renderHumanReviewActions,
    restoreConversationResult: handleConversationResult,
    runJobConversation,
  };
}
