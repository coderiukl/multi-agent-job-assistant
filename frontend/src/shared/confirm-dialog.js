/**
 * Accessible replacement for window.confirm built on the native <dialog>
 * declared in index.html (#confirm-dialog). Focus is trapped by the browser
 * and returned to the previously focused element on close.
 *
 * Resolves to true only when the user explicitly confirms.
 */
export function confirmAction({
  title,
  message,
  confirmLabel = "Xác nhận",
  cancelLabel = "Hủy",
  tone = "danger",
} = {}) {
  const dialog = document.querySelector("#confirm-dialog");

  if (!(dialog instanceof HTMLDialogElement) || typeof dialog.showModal !== "function") {
    return Promise.resolve(window.confirm(message || title || ""));
  }

  const titleElement = dialog.querySelector("#confirm-dialog-title");
  const messageElement = dialog.querySelector("#confirm-dialog-message");
  const acceptButton = dialog.querySelector("[data-confirm-accept]");
  const cancelButton = dialog.querySelector("[data-confirm-cancel]");
  const previouslyFocused = document.activeElement;

  titleElement.textContent = title || "Xác nhận";
  messageElement.textContent = message || "";
  acceptButton.textContent = confirmLabel;
  cancelButton.textContent = cancelLabel;
  acceptButton.className = tone === "danger"
    ? "btn btn-danger"
    : "btn btn-primary";
  dialog.dataset.tone = tone;
  dialog.returnValue = "";

  return new Promise((resolve) => {
    const handleClose = () => {
      dialog.removeEventListener("close", handleClose);
      resolve(dialog.returnValue === "confirm");

      if (previouslyFocused instanceof HTMLElement && previouslyFocused.isConnected) {
        previouslyFocused.focus();
      }
    };

    dialog.addEventListener("close", handleClose);
    dialog.showModal();
    cancelButton.focus();
  });
}
