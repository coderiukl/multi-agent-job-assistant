import { sendConversationMessage } from "../../api.js";
import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import { resumeConversation } from "../../api/conversation-api.js";

export function createChatController({
  addMessage,
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

    return {
      message:
        typedMessage ||
        (jobDescription ? defaultMatchingMessage : ""),
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
      );
      return;
    }

    await handleJobSearchConversation(
      originalMessage,
      conversation.jobSearchResult,
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

  function handleConversationError(error) {
    showError(
      error?.message ||
        "Đã xảy ra lỗi khi xử lý yêu cầu.",
    );

    addMessage({
      role: "assistant",
      text:
        "Mình chưa thể xử lý yêu cầu này. " +
        "Bạn hãy kiểm tra backend và thử lại.",
    });
  }

  function renderHumanReviewActions() {
    const container = document.createElement("div");

    container.className = "human-review-actions";

    const approveButton = document.createElement("button");
    approveButton.type = "button";
    approveButton.className = "human-review-approve";
    approveButton.textContent = "Tạo Cover Letter";

    const rejectButton = document.createElement("button");
    rejectButton.type = "button";
    rejectButton.className = "human-review-reject";
    rejectButton.textContent = "Bỏ qua";

    container.append(approveButton, rejectButton);

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

  async function handleHumanReviewDecision(action, container) {
    if (!state.pendingHumanReview) {
      return;
    }

    const buttons = container.querySelectorAll("button");

    buttons.forEach((button) => {
      button.disabled = true;
    });

    try {
      const result = await resumeConversation({
        threadId: state.threadId,
        action,
      });

      state.pendingHumanReview = null;

      container.remove();

      addMessage({
        role: "assistant",
        text: result.answer,
      });

      await handleConversationResult(result, "");
    } catch (error) {
      buttons.forEach((button) => {
        button.disabled = false;
      });

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
      cvId: state.selectedCvFile ? state.uploadedCvId : null,
      cvName: state.selectedCvFile
        ? state.uploadedCvName ?? state.selectedCvFile.name
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
        });

        renderHumanReviewActions();
        return;
      }

      addMessage({
        role: "assistant",
        text: conversation.answer,
      });

      await handleConversationResult(conversation, input.message);
    } catch (error) {
      handleConversationError(error);
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
        });

        renderHumanReviewActions();
        return;
      }

      rememberConversationResults(conversation, message);

      addMessage({
        role: "assistant",
        text: conversation.answer,
      });

      const result = getResult(conversation);

      if (result) {
        renderResult(result);
      }
    } catch (error) {
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
    restoreConversationResult: handleConversationResult,
    runJobConversation,
  };
}
