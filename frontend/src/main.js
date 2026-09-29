import { createThreadId } from "./core/conversation-storage.js";

import { state } from "./core/state.js";
import { elements } from "./core/elements.js";
import { createChatController } from "./features/chat/chat-controller.js";
import { createCareerAdviceRenderer } from "./features/career-advice/career-advice-renderer.js";
import { createCoverLetterRenderer } from "./features/cover-letter/cover-letter-renderer.js";
import { createHistoryController } from "./features/conversation-history/history-controller.js";
import { createCvController } from "./features/cv/cv-controller.js";
import { createCvAnalysisRenderer } from "./features/cv/cv-analysis-renderer.js";
import { createJobRenderer } from "./features/jobs/job-renderer.js";
import { createJobSearchRenderer } from "./features/jobs/job-search-renderer.js";
import { createJobsController } from "./features/jobs/jobs-controller.js";
import {
  renderInitialJobState,
  renderJobErrorState,
  renderJobLoading,
  renderNoJobResults,
} from "./features/jobs/job-states-renderer.js";
import { createWorkflowRecommendationsRenderer } from "./features/jobs/workflow-recommendations-renderer.js";
import { createMatchingRenderer } from "./features/matching/matching-renderer.js";
import { createWorkspaceController } from "./features/workspace/workspace-controller.js";
import {
  appendMessage,
  removeTypingIndicator as removeTyping,
  scrollMessagesToBottom as scrollToBottom,
  showTypingIndicator as showTyping,
} from "./features/chat/chat-renderer.js";

import "./css/index.css";

const RESULT_TYPES = [
  {
    type: "job_search",
    label: "Việc làm",
    field: "jobSearchResult",
  },
  {
    type: "job_matching",
    label: "So khớp",
    field: "jobMatchingResult",
  },
  {
    type: "cv_analysis",
    label: "Phân tích CV",
    field: "cvAnalysisResult",
  },
  {
    type: "career_advice",
    label: "Tư vấn",
    field: "careerAdviceResult",
  },
  {
    type: "cover_letter",
    label: "Cover Letter",
    field: "coverLetterResult",
  },
];

const {
  closeJobDetail,
  closeResultsPanel,
  handleMobileTabClick,
  isJobDetailOpen,
  openResultsPanel,
  setActiveWorkspacePanel,
  setResultsAvailability,
  toggleConversationHistory,
  toggleResultsPanel,
  trapJobDetailFocus,
  updateMobileResultsBadge,
} = createWorkspaceController();

const coverLetterRenderer = createCoverLetterRenderer({
  openResultsPanel,
  showError,
  updateMobileResultsBadge,
});

const careerAdviceRenderer = createCareerAdviceRenderer({
  openResultsPanel,
  updateMobileResultsBadge,
});

const matchingRenderer = createMatchingRenderer({
  openResultsPanel,
  updateMobileResultsBadge,
});

const cvAnalysisRenderer = createCvAnalysisRenderer({
  openResultsPanel,
  renderBreakdownItem:
    matchingRenderer.renderBreakdownItem,
  updateMobileResultsBadge,
});

const {
  openJobDetail,
  renderJobCard,
  renderJobDescriptionComposerSummary,
  showJobDescriptionEditor,
} = createJobRenderer({
  closeJobDetail,
  generateCoverLetterForJob,
  matchSelectedJob,
});

const jobSearchRenderer = createJobSearchRenderer({
  openResultsPanel,
  renderJobCard,
  showInitialJobState,
  showNoJobResults,
  updateMobileResultsBadge,
});

const workflowRecommendationsRenderer =
  createWorkflowRecommendationsRenderer({
    openResultsPanel,
    showNoJobResults,
    updateMobileResultsBadge,
  });

const historyController = createHistoryController({
  addMessage,
  resetConversation,
  showError,
});

const jobsController = createJobsController({
  clearError,
  renderJobSearchResult:
    jobSearchRenderer.renderJobSearchResult,
  showError,
  showJobErrorState,
  showJobLoading,
});

const chatController = createChatController({
  addMessage,
  clearError,
  clearComposerContextAfterSubmit,
  closeJobDetail,
  handleJobSearchConversation: jobsController.handleConversationSearch,
  rememberConversationThread: historyController.rememberConversationThread,
  rememberConversationResults,
  removeTypingIndicator,
  renderCareerAdviceResult:
    careerAdviceRenderer.renderCareerAdviceResult,
  renderCoverLetterResult:
    coverLetterRenderer.renderCoverLetterResult,
  renderCvAnalysisResult:
    cvAnalysisRenderer.renderCvAnalysisResult,
  renderJobMatchingResult:
    matchingRenderer.renderJobMatchingResult,
  renderWorkflowJobRecommendations:
    workflowRecommendationsRenderer.renderWorkflowJobRecommendations,
  resizeMessageInput,
  saveThreadId: historyController.saveThreadId,
  setComposerDisabled,
  showError,
  showTypingIndicator,
  updateComposerContext,
});

const cvController = createCvController({
  addMessage,
  clearError,
  showError,
  updateComposerContext,
});

initializeApplication().catch((error) => {
  console.error(
    "Application initialization failed:",
    error,
  );
});


async function initializeApplication() {
  bindEvents();
  resizeMessageInput();
  setActiveWorkspacePanel("chat");
  updateComposerContext();
  showInitialJobState();
  historyController.renderConversationHistory();

  const restored = await historyController.restoreConversationHistory();

  if (!restored) {
    addWelcomeMessage();
    return;
  }

  restoreConversationContext(restored);

  await restoreConversationResults(restored.results);
  await historyController.cacheCurrentConversation();
}

function rememberConversationResults(
  conversation,
  originalMessage = "",
  { renderTabs = true } = {},
) {
  for (const definition of RESULT_TYPES) {
    if (!conversation?.[definition.field]) {
      continue;
    }

    const entry = {
      type: definition.type,
      label: definition.label,
      conversation,
      originalMessage,
    };

    state.conversationResults = [
      ...state.conversationResults.filter(
        (item) => item.type !== definition.type,
      ),
      entry,
    ];
  }

  const routeEntry = state.conversationResults.find(
    (item) => item.type === conversation?.route,
  );

  if (routeEntry) {
    state.activeConversationResultType = routeEntry.type;
  }

  if (renderTabs) {
    renderResultHistoryTabs();
  }

  historyController.updateConversationThread(state.threadId, {
    hasCv: Boolean(state.uploadedCvId),
    hasJd: Boolean(state.jobDescription),
    resultTypes: state.conversationResults.map((item) => item.type),
  });
  historyController.cacheCurrentConversation();
}

async function restoreConversationResults(results) {
  state.conversationResults = [];
  state.activeConversationResultType = null;

  for (const storedResult of results ?? []) {
    rememberConversationResults(
      storedResult.conversation,
      storedResult.originalMessage,
      { renderTabs: false },
    );
  }

  renderResultHistoryTabs();

  const activeEntry = state.conversationResults.at(-1);

  if (activeEntry) {
    await showConversationResult(activeEntry.type);
  }
}

function renderResultHistoryTabs() {
  const container = elements.resultHistoryTabs;

  if (!container) {
    return;
  }

  container.innerHTML = "";
  container.hidden = state.conversationResults.length === 0;

  for (const entry of state.conversationResults) {
    const button = document.createElement("button");

    button.type = "button";
    button.className = "result-history-tab";
    button.dataset.resultType = entry.type;
    button.textContent = entry.label;
    button.classList.toggle(
      "is-active",
      entry.type === state.activeConversationResultType,
    );

    container.append(button);
  }
}

async function showConversationResult(type) {
  const entry = state.conversationResults.find(
    (item) => item.type === type,
  );

  if (!entry) {
    return;
  }

  state.activeConversationResultType = entry.type;
  renderResultHistoryTabs();

  const conversation = entry.conversation;

  if (entry.type === "job_search") {
    if (conversation.workflowJobMatches.length) {
      workflowRecommendationsRenderer.renderWorkflowJobRecommendations(
        conversation.jobSearchResult,
        conversation.workflowJobMatches,
        conversation.careerAdviceResult,
      );
      return;
    }

    await jobsController.handleConversationSearch(
      entry.originalMessage,
      conversation.jobSearchResult,
    );
    return;
  }

  const renderers = {
    job_matching: matchingRenderer.renderJobMatchingResult,
    cv_analysis: cvAnalysisRenderer.renderCvAnalysisResult,
    career_advice: careerAdviceRenderer.renderCareerAdviceResult,
    cover_letter: coverLetterRenderer.renderCoverLetterResult,
  };

  renderers[entry.type]?.(
    conversation[
      RESULT_TYPES.find((item) => item.type === entry.type)?.field
    ],
  );
}

function restoreConversationContext(history) {
  const context = history.latestContext ?? {};
  const cvId = context.cvId ?? history.cvId ?? null;
  const cvName = context.cvName ?? history.cvName ?? null;
  const jobDescription =
    context.jobDescription ?? history.jobDescription ?? "";

  state.uploadedCvId = cvId;
  state.uploadedCvName = cvName;
  state.selectedCvFile = null;
  state.cvUploadStatus = cvId ? "uploaded" : "idle";
  cvController.renderStatus();

  state.jobDescription = jobDescription;
  elements.jobDescriptionInput.value = jobDescription;

  if (jobDescription) {
    setMatchingMode(true, jobDescription);
  }
}

function addWelcomeMessage() {
  addMessage({
    role: "assistant",
    text:
      "Xin chào! Mình là Job Search AI. Mình có thể giúp bạn " +
      "tìm việc, phân tích CV và tư vấn định hướng nghề nghiệp.",
  }, { cache: false });
}

function bindEvents() {
  elements.messageInput.addEventListener(
    "input",
    () => {
      resizeMessageInput();
      updateSendButton();
    },
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
    chatController.handleSubmit,
  );

  elements.toggleJdButton.addEventListener(
    "click",
    () => setMatchingMode(!state.matchingMode),
  );

  elements.jobDescriptionInput.addEventListener(
    "input",
    handleJobDescriptionInput,
  );

  elements.mobileTabs?.addEventListener(
    "click",
    handleMobileTabClick,
  );

  elements.resultHistoryTabs?.addEventListener(
    "click",
    (event) => {
      const button = event.target.closest("[data-result-type]");

      if (button) {
        showConversationResult(button.dataset.resultType);
      }
    },
  );

  elements.clearJdButton.addEventListener(
    "click",
    clearJobDescription,
  );

  elements.editJdButton?.addEventListener(
    "click",
    showJobDescriptionEditor,
  );

  elements.attachCvButton.addEventListener(
    "click",
    () => {
      elements.cvInput.click();
    },
  );

  elements.cvInput.addEventListener(
    "change",
    cvController.handleSelection,
  );

  elements.removeCvButton.addEventListener(
    "click",
    cvController.remove,
  );

  elements.newChatButton.addEventListener(
    "click",
    resetConversation,
  );

  elements.toggleResultsButton?.addEventListener(
    "click",
    toggleResultsPanel,
  );
  
  elements.sidebarNewChatButton?.addEventListener(
    "click",
    resetConversation,
  );

  elements.historyEmptyNewChatButton?.addEventListener(
    "click",
    resetConversation,
  );

  elements.conversationHistorySearch?.addEventListener(
    "input",
    (event) => {
      historyController.setSearchQuery(event.target.value);
    },
  );

  elements.toggleHistoryButton?.addEventListener(
    "click",
    toggleConversationHistory,
  );

  elements.conversationHistoryList?.addEventListener(
    "click",
    historyController.handleHistoryClick,
  );

  document.addEventListener(
    "click",
    historyController.handleDocumentClick,
  );

  elements.suggestionList.addEventListener(
    "click",
    handleSuggestionClick,
  );

  elements.composerActions?.addEventListener(
    "click",
    handleSuggestionClick,
  );

  elements.jobResults.addEventListener(
    "click",
    handleJobResultClick,
  );

  elements.jobPagination?.addEventListener(
    "click",
    (event) => {
      const button = event.target.closest("[data-job-page]");

      if (button && !button.disabled) {
        jobsController.handlePageChange(Number(button.dataset.jobPage));
      }
    },
  );

  elements.jobSort.addEventListener(
    "change",
    jobsController.handleSortChange,
  );

  elements.backToJobsButton?.addEventListener(
    "click",
    jobSearchRenderer.showJobSearchResultsFromState,
  );

  elements.closeResultsButton?.addEventListener(
    "click",
    closeResultsPanel,
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
    historyController.handleDocumentKeydown(event);

    if (event.key === "Escape") {
      closeJobDetail();
      return;
    }

    if (
      event.key === "Tab" &&
      isJobDetailOpen()
    ) {
      trapJobDetailFocus(event);
    }
  });
}


function setMatchingMode(
  enabled,
  jobDescription = "",
  matchingJob = null,
) {
  state.matchingMode = enabled;

  if (jobDescription) {
    state.jobDescription = jobDescription;
    elements.jobDescriptionInput.value = jobDescription;
  }

  elements.jobDescriptionPanel.hidden = !enabled;
  renderJobDescriptionComposerSummary(matchingJob);
  elements.toggleJdButton.classList.toggle("is-active", enabled);
  elements.toggleJdButton.setAttribute(
    "aria-pressed",
    String(enabled),
  );

  updateJobDescriptionCount();
  updateSendButton();
  updateComposerContext();

  if (enabled && !matchingJob) {
    elements.jobDescriptionInput.focus();
  }
}


function handleJobDescriptionInput(event) {
  state.jobDescription = event.target.value;
  renderJobDescriptionComposerSummary(null);
  updateJobDescriptionCount();
  updateSendButton();
}


function clearJobDescription() {
  state.jobDescription = "";
  elements.jobDescriptionInput.value = "";
  renderJobDescriptionComposerSummary(null);
  updateJobDescriptionCount();
  updateSendButton();
  elements.jobDescriptionInput.focus();
}


function clearComposerContextAfterSubmit() {
  state.selectedCvFile = null;
  elements.cvInput.value = "";
  cvController.renderStatus();

  state.jobDescription = "";
  elements.jobDescriptionInput.value = "";
  setMatchingMode(false);
}


function updateJobDescriptionCount() {
  const length = elements.jobDescriptionInput.value.length;
  elements.jobDescriptionCount.textContent =
    `${length.toLocaleString("vi-VN")}/20.000`;
}


function handleSuggestionClick(event) {
  const coverLetterButton = event.target.closest(
    "[data-action='open-cover-letter']",
  );

  if (coverLetterButton) {
    setMatchingMode(true);

    elements.messageInput.value =
      "Hãy viết thư ứng tuyển dựa trên CV " +
      "và công việc này";

    elements.suggestionList.hidden = true;
    elements.messageInput.focus();

    resizeMessageInput();
    updateSendButton();
    return;
  }

  const matchingButton = event.target.closest(
    "[data-action='open-matching']",
  );

  if (matchingButton) {
    setMatchingMode(true);
    elements.messageInput.value =
      "Hãy đánh giá mức độ phù hợp giữa CV của tôi và công việc này";
    elements.suggestionList.hidden = true;
    resizeMessageInput();
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
  resizeMessageInput();
  updateSendButton();
}


function handleJobResultClick(event) {
  const coverLetterButton = event.target.closest(
    "[data-action='cover-letter-job']",
  );

  const copyCoverLetterButton = event.target.closest(
    "[data-action='copy-cover-letter']",
  );

  if (copyCoverLetterButton) {
    coverLetterRenderer.copyCoverLetter(
      copyCoverLetterButton,
    );
    return;
  }

  const matchingButton = event.target.closest(
    "[data-action='match-job']",
  );

  const detailButton = event.target.closest(
    "[data-action='view-job']",
  );

  const actionButton =
    coverLetterButton ||
    matchingButton ||
    detailButton;

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
    matchSelectedJob(hit);
    return;
  }

  if (coverLetterButton) {
    generateCoverLetterForJob(hit);
    return;
  }

  openJobDetail(hit);
}

async function generateCoverLetterForJob(hit) {
  const job = hit?.job ?? {};

  await chatController.runJobConversation({
    hit,
    message: `Viết thư ứng tuyển cho vị trí ${job.title || "này"}`,
    getResult: (conversation) => conversation.coverLetterResult,
    renderResult:
      coverLetterRenderer.renderCoverLetterResult,
    missingDescriptionMessage: "Công việc này chưa có JD để tạo thư ứng tuyển.",
    requestErrorMessage: "Không thể tạo thư ứng tuyển.",
    assistantErrorMessage: "Mình chưa thể tạo thư ứng tuyển. Bạn hãy kiểm tra backend và thử lại.",
  });
}

async function matchSelectedJob(hit) {
  const job = hit?.job ?? {};

  await chatController.runJobConversation({
    hit,
    message: `Đánh giá CV của tôi với vị trí ${job.title || "này"}`,
    getResult: (conversation) => conversation.jobMatchingResult,
    renderResult:
      matchingRenderer.renderJobMatchingResult,
    missingDescriptionMessage: "Công việc này chưa có JD để thực hiện so khớp.",
    requestErrorMessage: "Không thể so khớp CV với công việc này.",
    assistantErrorMessage: "Mình chưa thể so khớp CV với công việc này. Bạn hãy kiểm tra backend và thử lại.",
  });
}

function showJobLoading() {
  openResultsPanel();
  renderJobLoading();
}


function showInitialJobState() {
  updateMobileResultsBadge(0);
  renderInitialJobState();
}


function showNoJobResults() {
  renderNoJobResults();
}


function showJobErrorState() {
  renderJobErrorState();
}


function resetConversation() {
  const nextThreadId = createThreadId();

  historyController.saveThreadId(nextThreadId);
  state.messages = [];
  state.jobs = [];
  state.currentSearchResult = null;
  state.lastSearchQuery = "";
  state.currentSort = "relevance";
  state.selectedJob = null;
  state.currentWorkflow = null;
  state.workflowJobMatches = [];
  state.conversationResults = [];
  state.activeConversationResultType = null;
  state.currentMatchingResult = null;
  state.currentCvAnalysisResult = null;
  state.currentCareerAdviceResult = null;
  state.currentCoverLetterResult = null;
  state.selectedCvFile = null;
  state.uploadedCvId = null;
  state.uploadedCvName = null;
  state.cvUploadStatus = "idle";
  state.cvUploadRequestId += 1;
  state.matchingMode = false;
  state.jobDescription = "";
  state.isSending = false;
  state.isJobSearchLoading = false;

  elements.messageList.innerHTML = "";
  elements.suggestionList.hidden = false;
  elements.messageInput.value = "";
  if (elements.conversationHistorySearch) {
    elements.conversationHistorySearch.value = "";
    historyController.setSearchQuery("");
  }
  resizeMessageInput();
  elements.jobDescriptionInput.value = "";
  elements.cvInput.value = "";
  cvController.renderStatus();
  elements.jobSort.value = "relevance";
  renderResultHistoryTabs();

  setMatchingMode(false);

  clearError();
  closeJobDetail();
  showInitialJobState();
  closeResultsPanel();
  setResultsAvailability(false);
  updateSendButton();

  addMessage({
    role: "assistant",
    text:
      "Cuộc trò chuyện mới đã bắt đầu. " +
      "Bạn muốn tìm công việc hay cần hỗ trợ về CV?",
  }, { cache: false });
}


function addMessage({
  role,
  text,
  context = null,
  result = null,
}, { cache = true } = {}) {
  const message = {
    id: crypto.randomUUID(),
    role,
    text,
    context,
    result,
  };

  state.messages.push(message);

  appendMessage(elements.messageList, message);

  if (cache) {
    historyController.cacheCurrentConversation();
  }

  scrollMessagesToBottom();
}

function showTypingIndicator() {
  showTyping(elements.messageList);
  scrollMessagesToBottom();
}

function removeTypingIndicator() {
  removeTyping(elements.messageList);
}

function scrollMessagesToBottom() {
  scrollToBottom(elements.messageList);
}

function setComposerDisabled(disabled) {
  elements.messageInput.disabled = disabled;
  elements.attachCvButton.disabled = disabled;
  elements.toggleJdButton.disabled = disabled;
  elements.jobDescriptionInput.disabled = disabled;
  elements.clearJdButton.disabled = disabled;

  elements.sendButton.disabled =
    disabled || !hasComposerContent();
}

function updateComposerContext() {
  if (!elements.messageInput) {
    return;
  }

  const hasCv = Boolean(state.uploadedCvId);

  elements.chatForm?.setAttribute(
    "data-mode",
    state.matchingMode ? "matching" : "search",
  );

  elements.chatForm?.setAttribute(
    "data-cv-ready",
    String(hasCv),
  );

  elements.messageInput.placeholder = state.matchingMode
    ? "Nhập yêu cầu so khớp, ví dụ: đánh giá CV này với JD..."
    : hasCv
      ? "Tìm việc phù hợp với CV, kỹ năng hoặc mục tiêu tiếp theo..."
      : "Nhập vị trí, kỹ năng, địa điểm hoặc câu hỏi nghề nghiệp...";
}



function resizeMessageInput() {
  const textarea = elements.messageInput;

  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
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
