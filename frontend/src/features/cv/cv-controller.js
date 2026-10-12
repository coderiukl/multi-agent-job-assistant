import {
  deleteCv,
  getCvProcessingTask,
  updateCvProfile,
  uploadCv,
} from "../../api.js";
import { elements } from "../../core/elements.js";
import { state } from "../../core/state.js";
import {
  getClipboardImageFiles,
  validateCvFiles,
} from "./cv-validator.js";
import {
  readCvProfileEditor,
  renderCvProfileEditor,
} from "./cv-profile-editor.js";

export function createCvController({
  addMessage,
  clearError,
  showError,
  updateComposerContext,
}) {
  let previewEntries = [];
  let appendNextSelection = false;

  const sleep = (milliseconds) => new Promise(
    (resolve) => setTimeout(resolve, milliseconds),
  );

  function releasePreviewUrls() {
    for (const entry of previewEntries) {
      URL.revokeObjectURL(entry.url);
    }
    previewEntries = [];
  }

  function renderPreviews(files) {
    if (!elements.cvPreviewList) {
      return;
    }

    const imageFiles = files.filter((file) => file.type?.startsWith("image/"));
    const previewsAreCurrent =
      previewEntries.length === imageFiles.length &&
      previewEntries.every((entry, index) => entry.file === imageFiles[index]);

    if (!previewsAreCurrent) {
      releasePreviewUrls();
      previewEntries = imageFiles.map((file) => ({
        file,
        url: URL.createObjectURL(file),
      }));
    }

    elements.cvPreviewList.replaceChildren();
    for (const [index, entry] of previewEntries.entries()) {
      const item = document.createElement("div");
      item.className = "cv-preview-item";
      item.setAttribute("role", "listitem");
      item.title = `Trang ${index + 1}: ${entry.file.name}`;

      const image = document.createElement("img");
      image.className = "cv-preview-image";
      image.src = entry.url;
      image.alt = `Xem trước trang ${index + 1} của CV`;

      const pageNumber = document.createElement("span");
      pageNumber.className = "cv-preview-index";
      pageNumber.textContent = String(index + 1);

      item.append(image, pageNumber);
      elements.cvPreviewList.append(item);
    }
    elements.cvPreviewList.hidden = previewEntries.length === 0;
  }

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
    const files = state.selectedCvFiles?.length
      ? state.selectedCvFiles
      : (file ? [file] : []);
    const hasStoredCv = Boolean(state.uploadedCvId);
    const imageCount = files.filter(
      (selectedFile) => selectedFile.type?.startsWith("image/"),
    ).length;

    renderPreviews(files);

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
    elements.selectedCvName.textContent = files.length > 1
      ? `CV gồm ${files.length}/5 ảnh`
      : (
        (imageCount === 1 ? `${file?.name} · 1/5 ảnh` : file?.name) ||
        state.uploadedCvName ||
        "CV đã tải lên"
      );
    if (elements.cvFileTypeBadge) {
      const fileName = (file?.name || state.uploadedCvName || "").toLowerCase();
      elements.cvFileTypeBadge.textContent = files.length > 1
        ? `${files.length} ẢNH`
        : (fileName.endsWith(".pdf") ? "PDF" : "ẢNH");
    }

    const statuses = {
      uploading: {
        description: imageCount
          ? (
            hasStoredCv
              ? `Đã tải ${imageCount} ảnh · đang OCR và phân tích...`
              : `Đang tải lên ${imageCount} ảnh CV...`
          )
          : (
            hasStoredCv
              ? "Đã tải CV · đang phân tích..."
              : "Đang tải CV lên..."
          ),
        badge: imageCount
          ? (
            hasStoredCv
              ? `Đang xử lý ${imageCount} trang`
              : `Đang tải ${imageCount} ảnh`
          )
          : "Đang xử lý CV",
        className: "cv-status-badge is-busy",
      },
      uploaded: {
        description: state.uploadedCvProfile?.needs_review
          ? `Đã xử lý${imageCount ? ` ${imageCount} trang` : ""} · cần kiểm tra`
          : `Đã xử lý${imageCount ? ` ${imageCount} trang` : " CV"} thành công`,
        badge: state.uploadedCvProfile?.needs_review
          ? "Cần kiểm tra CV"
          : "CV sẵn sàng",
        className: state.uploadedCvProfile?.needs_review
          ? "cv-status-badge is-busy"
          : "cv-status-badge is-ready",
      },
      failed: {
        description: imageCount
          ? `Tải lên hoặc xử lý ${imageCount} ảnh thất bại`
          : "Tải lên hoặc phân tích thất bại",
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
    elements.selectedCv.classList.toggle(
      "is-uploading",
      state.cvUploadStatus === "uploading",
    );
    elements.selectedCv.classList.toggle(
      "is-failed",
      state.cvUploadStatus === "failed",
    );
    elements.selectedCv.classList.toggle(
      "is-uploaded",
      state.cvUploadStatus === "uploaded",
    );
    elements.selectedCv.setAttribute(
      "aria-busy",
      String(state.cvUploadStatus === "uploading"),
    );
    if (elements.reviewCvButton) {
      elements.reviewCvButton.hidden = !state.uploadedCvProfile;
    }
    if (elements.addCvPagesButton) {
      elements.addCvPagesButton.hidden = !(
        imageCount > 0 &&
        imageCount < 5 &&
        state.cvUploadStatus !== "uploading"
      );
      elements.addCvPagesButton.textContent = `+ Thêm (${imageCount}/5)`;
    }
    updateComposerContext();
  }

  async function handleFiles(files, { announceCompletion = true } = {}) {
    const selectedFiles = Array.from(files ?? []);
    if (!selectedFiles.length) {
      return;
    }

    const validationError = validateCvFiles(selectedFiles);

    if (validationError) {
      showError(validationError);
      elements.cvInput.value = "";
      return;
    }

    clearError();

    const previousCv = state.uploadedCvId
      ? {
        file: state.selectedCvFile,
        files: [...(state.selectedCvFiles ?? [])],
        id: state.uploadedCvId,
        name: state.uploadedCvName,
        profile: state.uploadedCvProfile,
        taskId: state.uploadedCvTaskId,
      }
      : null;

    const requestId = state.cvUploadRequestId + 1;

    state.cvUploadRequestId = requestId;
    state.selectedCvFiles = selectedFiles;
    state.selectedCvFile = selectedFiles[0];
    state.uploadedCvId = null;
    state.uploadedCvName = null;
    state.uploadedCvProfile = null;
    state.uploadedCvTaskId = null;
    state.cvUploadStatus = "uploading";
    renderStatus();

    try {
      const result = await uploadCv(selectedFiles);

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

      if (previousCv?.id && previousCv.id !== result.fileId) {
        try {
          await deleteCv(previousCv.id);
        } catch (cleanupError) {
          console.warn("Could not delete the replaced CV.", cleanupError);
        }
      }

      if (announceCompletion) {
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
      }
    } catch (error) {
      if (state.cvUploadRequestId !== requestId) {
        return;
      }

      const failedCvId = state.uploadedCvId;
      if (previousCv) {
        state.selectedCvFile = previousCv.file;
        state.selectedCvFiles = previousCv.files;
        state.uploadedCvId = previousCv.id;
        state.uploadedCvName = previousCv.name;
        state.uploadedCvProfile = previousCv.profile;
        state.uploadedCvTaskId = previousCv.taskId;
        state.cvUploadStatus = "uploaded";
      } else {
        if (!failedCvId) {
          state.uploadedCvName = null;
        }
        state.uploadedCvProfile = null;
        state.cvUploadStatus = "failed";
      }
      renderStatus();
      if (failedCvId && failedCvId !== previousCv?.id) {
        deleteCv(failedCvId).catch(() => {});
      }
      showError(error?.message || "Không thể tải CV lên backend.");
    }
  }

  function handleSelection(event) {
    const incomingFiles = Array.from(event.target.files ?? []);
    const currentFiles = state.selectedCvFiles ?? [];
    const files = appendNextSelection
      ? [...currentFiles, ...incomingFiles]
      : incomingFiles;

    appendNextSelection = false;
    return handleFiles(files);
  }

  function openFilePicker() {
    const currentFiles = state.selectedCvFiles ?? [];

    if (state.cvUploadStatus === "uploading") {
      showError("Hãy đợi CV hiện tại xử lý xong trước khi thêm ảnh.");
      return;
    }

    if (currentFiles.length >= 5) {
      showError("CV đã đủ tối đa 5 ảnh.");
      return;
    }

    appendNextSelection = (
      currentFiles.length > 0 &&
      currentFiles.every((file) => file.type?.startsWith("image/"))
    );
    elements.cvInput.value = "";
    elements.cvInput.click();
  }

  function normalizePastedImage(file) {
    const extensionsByType = {
      "image/jpeg": [".jpg", ".jpeg"],
      "image/png": [".png"],
    };
    const allowedExtensions = extensionsByType[file.type] ?? [];
    const normalizedName = (file.name || "").toLowerCase();

    if (allowedExtensions.some((extension) => normalizedName.endsWith(extension))) {
      return file;
    }

    if (!allowedExtensions.length) {
      return file;
    }

    return new File(
      [file],
      `cv-pasted-${Date.now()}${allowedExtensions[0]}`,
      {
        type: file.type,
        lastModified: file.lastModified || Date.now(),
      },
    );
  }

  function handlePaste(event) {
    const imageFiles = getClipboardImageFiles(event.clipboardData);

    if (!imageFiles.length) {
      return;
    }

    event.preventDefault();

    if (state.cvUploadStatus === "uploading") {
      showError("Hãy đợi CV hiện tại xử lý xong trước khi thêm ảnh.");
      return;
    }

    const currentFiles = state.selectedCvFiles ?? [];
    const normalizedFiles = imageFiles.map(normalizePastedImage);
    const files = currentFiles.length
      ? [...currentFiles, ...normalizedFiles]
      : normalizedFiles;

    void handleFiles(
      files,
      { announceCompletion: false },
    );
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
    state.selectedCvFiles = [];
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

    renderCvProfileEditor(
      elements.cvProfileEditor,
      state.uploadedCvProfile,
    );
    elements.cvProfileDialog.showModal();
  }

  async function saveProfileReview() {
    if (!state.uploadedCvId) {
      return;
    }

    const profile = readCvProfileEditor(
      elements.cvProfileEditor,
      state.uploadedCvProfile,
    );

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
    handleFiles,
    handlePaste,
    handleSelection,
    openFilePicker,
    remove,
    openProfileReview,
    renderStatus,
    saveProfileReview,
  };
}
