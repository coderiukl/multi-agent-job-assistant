import {getOrCreateThreadId, loadConversationThreads} from "./conversation-storage.js";

export const state = {
    threadId: getOrCreateThreadId(),
    conversationThreads: loadConversationThreads(),
    messages: [],

    selectedCvFile: null,
    uploadedCvId: null,
    uploadedCvName: null,
    uploadedCvProfile: null,
    uploadedCvTaskId: null,
    cvUploadStatus: "idle",
    cvUploadRequestId: 0,

    matchingMode: false,
    jobDescription: "",

    currentMatchingResult: null,
    currentCvAnalysisResult: null,
    currentCareerAdviceResult: null,
    currentCoverLetterResult: null,

    currentWorkflow: null,
    workflowJobMatches: [],
    conversationResults: [],
    activeConversationResultType: null,

    isSending: false,
    isJobSearchLoading: false,
    
    jobs: [],
    currentSearchResult: null,
    lastSearchQuery: "",
    currentSort: "relevance",
    selectedJob: null,

    activeWorkspacePanel: "chat",
    historyOpen: true,
    resultsOpen: false,
    resultsAvailable: false,
    lastFocusedBeforeDrawer: null,

    pendingHumanReview: null,
};
