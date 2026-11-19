import { createIcon } from "./icons.js";

const TOAST_DURATION_MS = 2800;

/**
 * Short, non-blocking confirmation of a completed action (e.g. "copied").
 * Errors stay in inline alerts next to the control that caused them.
 */
export function showToast(message, { tone = "success" } = {}) {
  const region = document.querySelector("#toast-region");

  if (!region || !message) {
    return;
  }

  const toast = document.createElement("div");

  toast.className = `toast is-${tone}`;
  toast.append(
    createIcon(tone === "success" ? "check" : "info"),
    document.createTextNode(message),
  );

  region.append(toast);

  window.setTimeout(() => {
    toast.classList.add("is-leaving");
    toast.addEventListener("transitionend", () => toast.remove(), { once: true });
    window.setTimeout(() => toast.remove(), 400);
  }, TOAST_DURATION_MS);
}
