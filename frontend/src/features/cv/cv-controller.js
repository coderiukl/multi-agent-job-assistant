import { uploadCv } from "../../api.js";
import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import { validateCvFile } from "./cv-validator.js";

export function createCvController({
  addMessage,
  clearError,
  showError,
  updateComposerContext,
}) {
  function renderStatus() {
    const file = state.selectedCvFile;

    if (!file) {
      elements.selectedCv.hidden = true;
      elements.cvStatusBadge.textContent = "Chưa có CV";
      elements.cvStatusBadge.className = "cv-status-badge";
      updateComposerContext();
      return;
    }

    elements.selectedCv.hidden = false;
    elements.selectedCvName.textContent = file.name;

    const statuses = {
      uploading: {
        description: "Đang tải lên và phân tích...",
        badge: "Đang xử lý CV",
        className: "cv-status-badge is-busy",
      },
      uploaded: {
        description: "Đã tải lên và phân tích thành công",
        badge: "CV sẵn sàng",
        className: "cv-status-badge is-ready",
      },
      failed: {
        description: "Tải lên hoặc phân tích thất bại",
        badge: "CV bị lỗi",
        className: "cv-status-badge is-error",
      },
      idle: {
        description: "Đã chọn CV",
        badge: "Đã chọn CV",
        className: "cv-status-badge",
      },
    };
    const status = statuses[state.cvUploadStatus] ?? statuses.idle;

    elements.selectedCvStatus.textContent = status.description;
    elements.cvStatusBadge.textContent = status.badge;
    elements.cvStatusBadge.className = status.className;
    updateComposerContext();
  }

  async function handleSelection(event) {
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
    renderStatus();

    try {
      const result = await uploadCv(file);

      if (state.cvUploadRequestId !== requestId) {
        return;
      }

      if (!result.fileId) {
        throw new Error("Backend không trả về file_id của CV.");
      }

      state.uploadedCvId = result.fileId;
      state.cvUploadStatus = "uploaded";
      renderStatus();

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
      renderStatus();
      showError(error?.message || "Không thể tải CV lên backend.");
    }
  }

  function remove() {
    state.cvUploadRequestId += 1;
    state.selectedCvFile = null;
    state.uploadedCvId = null;
    state.cvUploadStatus = "idle";
    elements.cvInput.value = "";

    renderStatus();
    clearError();
  }

  return {
    handleSelection,
    remove,
    renderStatus,
  };
}
