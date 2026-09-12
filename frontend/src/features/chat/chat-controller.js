import { sendConversationMessage } from "../../api.js";
import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";

export function createChatController({
  addMessage,
  clearError,
  closeJobDetail,
  handleJobSearchConversation,
  rememberConversationThread,
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

    addMessage({ role: "user", text: input.message });
    rememberConversationThread({
      threadId: state.threadId,
      firstMessage: input.message,
    });

    clearComposerAfterSubmit();
    setComposerDisabled(true);
    showTypingIndicator();

    try {
      const conversation = await sendConversationMessage({
        threadId: state.threadId,
        message: input.message,
        cvId: state.uploadedCvId,
        jobDescription: input.jobDescription,
      });

      if (conversation.threadId) {
        saveThreadId(conversation.threadId);
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

    addMessage({ role: "user", text: message });
    rememberConversationThread({
      threadId: state.threadId,
      firstMessage: message,
    });
    elements.suggestionList.hidden = true;

    setComposerDisabled(true);
    showTypingIndicator();

    try {
      const conversation = await sendConversationMessage({
        threadId: state.threadId,
        message,
        cvId: state.uploadedCvId,
        jobDescription: description,
      });

      if (conversation.threadId) {
        saveThreadId(conversation.threadId);
      }

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
    runJobConversation,
  };
}
