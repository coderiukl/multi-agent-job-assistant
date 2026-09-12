import {getOrCreateThreadId, loadConversationThreads} from "./conversation-storage.js";

export const state = {
    threadId: getOrCreateThreadId(),
    conversationThreads: loadConversationThreads(),
    messages: [],

    selectedCvFile: null,
    uploadedCvId: null,
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
};
