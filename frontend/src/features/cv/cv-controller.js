import {
  deleteCv,
  getCvProcessingTask,
  updateCvProfile,
  uploadCv,
} from "../../api.js";
import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import { validateCvFile } from "./cv-validator.js";

export function createCvController({
  addMessage,
  clearError,
  showError,
  updateComposerContext,
}) {
  const sleep = (milliseconds) => new Promise(
    (resolve) => setTimeout(resolve, milliseconds),
  );

  async function waitForProcessing(taskId, requestId) {
    let delay = 750;

    while (state.cvUploadRequestId === requestId) {
      let task;
      try {
        task = await getCvProcessingTask(taskId);
      } catch (error) {
        if (error?.status === 401 || error?.status === 404) {
          throw error;
        }
        await sleep(delay);
        delay = Math.min(Math.round(delay * 1.6), 5000);
        continue;
      }

      if (task.status === "completed") {
        return task;
      }
      if (task.status === "failed") {
        throw new Error(
          task.errorMessage || "Backend không thể phân tích CV.",
        );
      }

      await sleep(delay);
      delay = Math.min(Math.round(delay * 1.6), 5000);
    }

    return null;
  }

  function renderStatus() {
    const file = state.selectedCvFile;
    const hasStoredCv = Boolean(state.uploadedCvId);

    if (!file && !hasStoredCv) {
      elements.selectedCv.hidden = true;
      elements.cvStatusBadge.textContent = "Chưa có CV";
      elements.cvStatusBadge.className = "cv-status-badge";
      if (elements.reviewCvButton) {
        elements.reviewCvButton.hidden = true;
      }
      updateComposerContext();
      return;
    }

    elements.selectedCv.hidden = false;
    elements.selectedCvName.textContent = (
      file?.name ||
      state.uploadedCvName ||
      "CV đã tải lên"
    );

    const statuses = {
      uploading: {
        description: "Đang tải lên và phân tích...",
        badge: "Đang xử lý CV",
        className: "cv-status-badge is-busy",
      },
      uploaded: {
        description: state.uploadedCvProfile?.needs_review
          ? "Đã phân tích · cần kiểm tra thông tin"
          : "Đã tải lên và phân tích thành công",
        badge: state.uploadedCvProfile?.needs_review
          ? "Cần kiểm tra CV"
          : "CV sẵn sàng",
        className: state.uploadedCvProfile?.needs_review
          ? "cv-status-badge is-busy"
          : "cv-status-badge is-ready",
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
    if (elements.reviewCvButton) {
      elements.reviewCvButton.hidden = !state.uploadedCvProfile;
    }
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
    state.uploadedCvName = null;
    state.uploadedCvProfile = null;
    state.uploadedCvTaskId = null;
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
      if (!result.taskId) {
        throw new Error("Backend không trả về task_id xử lý CV.");
      }

      state.uploadedCvId = result.fileId;
      state.uploadedCvName = result.fileName;
      state.uploadedCvTaskId = result.taskId;
      state.cvUploadStatus = "uploading";
      renderStatus();

      const completedTask = await waitForProcessing(
        result.taskId,
        requestId,
      );
      if (!completedTask || state.cvUploadRequestId !== requestId) {
        return;
      }

      state.uploadedCvProfile = completedTask.profile;
      state.cvUploadStatus = "uploaded";
      renderStatus();

      addMessage({
        role: "assistant",
        text: completedTask.profile?.needs_review
          ? (
            "CV “" + result.fileName + "” đã được phân tích nhưng có " +
            "thông tin chưa chắc chắn. Hãy chọn “Xem & sửa” trước khi matching."
          )
          : (
            "CV “" + result.fileName + "” đã được tải lên " +
            "và phân tích thành công."
          ),
      });
    } catch (error) {
      if (state.cvUploadRequestId !== requestId) {
        return;
      }

      if (!state.uploadedCvId) {
        state.uploadedCvName = null;
      }
      state.uploadedCvProfile = null;
      state.cvUploadStatus = "failed";
      renderStatus();
      showError(error?.message || "Không thể tải CV lên backend.");
    }
  }

  async function remove() {
    const cvId = state.uploadedCvId;

    if (cvId) {
      try {
        await deleteCv(cvId);
      } catch (error) {
        showError(error?.message || "Không thể xóa CV.");
        return;
      }
    }

    state.cvUploadRequestId += 1;
    state.selectedCvFile = null;
    state.uploadedCvId = null;
    state.uploadedCvName = null;
    state.uploadedCvProfile = null;
    state.uploadedCvTaskId = null;
    state.cvUploadStatus = "idle";
    elements.cvInput.value = "";

    renderStatus();
    clearError();
  }

  function openProfileReview() {
    if (!state.uploadedCvProfile || !elements.cvProfileDialog) {
      return;
    }

    elements.cvProfileEditor.value = JSON.stringify(
      state.uploadedCvProfile,
      null,
      2,
    );
    elements.cvProfileDialog.showModal();
  }

  async function saveProfileReview() {
    if (!state.uploadedCvId) {
      return;
    }

    let profile;
    try {
      profile = JSON.parse(elements.cvProfileEditor.value);
    } catch {
      showError("Thông tin CV không phải JSON hợp lệ.");
      return;
    }

    try {
      const updated = await updateCvProfile(
        state.uploadedCvId,
        profile,
      );
      state.uploadedCvProfile = updated;
      elements.cvProfileDialog.close();
      clearError();
      addMessage({
        role: "assistant",
        text: "Thông tin CV đã được cập nhật và sẽ được dùng cho matching.",
      });
    } catch (error) {
      showError(error?.message || "Không thể cập nhật thông tin CV.");
    }
  }

  return {
    handleSelection,
    remove,
    openProfileReview,
    renderStatus,
    saveProfileReview,
  };
}
