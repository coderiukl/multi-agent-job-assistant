import {
  getCurrentUser,
  loginAccount,
  registerAccount,
} from "../../api/auth-api.js";
import {
  clearAccessToken,
  getAccessToken,
  saveAccessToken,
  getStoredUserId,
  revisionKey,
} from "../../core/auth-storage.js";
import { elements } from "../../core/elements.js";

export function createAuthController({ clearPrivateData }) {
  let isSubmitting = false;
  let isLoggingOut = false;

  function bindEvents() {
    elements.authTabs?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-auth-view]");
      if (button) showAuthView(button.dataset.authView);
    });

    elements.loginForm?.addEventListener("submit", handleLogin);
    elements.registerForm?.addEventListener("submit", handleRegister);
    elements.logoutButton?.addEventListener("click", () => logout());
    elements.mobileLogoutButton?.addEventListener("click", () => logout());
    window.addEventListener("auth:unauthorized", () => {logout({ expired: true })});
    window.addEventListener("pageshow", (event) => {
      if (event.persisted) {
        elements.appShell.hidden = true;
        window.location.reload();
        return;
      }

      if (getStoredUserId() && !getAccessToken()) {
        logout({ expired: true });
      }
    });
  }

  async function restoreSession() {
    if (!getAccessToken()) {
      clearAccessToken();
      await clearPrivateData();
      showAuthScreen();
      return null;
    }

    try {
      return await getCurrentUser();
    } catch (error) {
      if (error?.status === 401) {
        await logout({ expired: true});
        return null
      }

      showAuthScreen(
        error?.message || "Không thể kết nối với dịch vụ xác thực.",
      );
    }
  }

  async function handleLogin(event) {
    event.preventDefault();
    if (isSubmitting || !event.currentTarget.reportValidity()) return;

    const email = elements.loginEmail.value.trim().toLowerCase();
    const password = elements.loginPassword.value;

    await submitAuth(
      () => loginAccount({ email, password }),
      elements.loginForm,
    );
  }

  async function handleRegister(event) {
    event.preventDefault();
    if (isSubmitting || !event.currentTarget.reportValidity()) return;

    const email = elements.registerEmail.value.trim().toLowerCase();
    const password = elements.registerPassword.value;
    const confirmation = elements.registerPasswordConfirmation.value;

    if (password !== confirmation) {
      showError("Mật khẩu xác nhận chưa trùng khớp.");
      elements.registerPasswordConfirmation.focus();
      return;
    }

    await submitAuth(async () => {
      await registerAccount({ email, password });
      return loginAccount({ email, password });
    }, elements.registerForm);
  }

  async function submitAuth(operation, form) {
    setSubmitting(form, true);
    showError("");

    try {
      const result = await operation();
      saveAccessToken(result.access_token);
      window.location.reload();
    } catch (error) {
      showError(getFriendlyAuthError(error));
      setSubmitting(form, false);
    }
  }

  async function logout({ expired = false } = {}) {
    if (isLoggingOut) return;

    isLoggingOut = true;
    isSubmitting = true;

    const userId = getStoredUserId();

    clearAccessToken();

    showAuthScreen(expired ? "Phiên đăng nhập đã hết hạn." : "");
    
    try {
      await clearPrivateData(userId);
    } catch (error) {
      console.error("Private cache cleanup failed.", error);
      showError("Chưa xóa được cache. Hãy tải lại rang trước khi đăng nhập.");

      return;
    }

    if (expired) {
      sessionStorage.setItem(
        "multi-agent-job-assistant-auth-message",
        "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
      );
    }

    window.location.reload();
  }

  function showAuthView(view) {
    const isRegister = view === "register";
    elements.loginForm.hidden = isRegister;
    elements.registerForm.hidden = !isRegister;
    elements.authLoginTab.classList.toggle("is-active", !isRegister);
    elements.authRegisterTab.classList.toggle("is-active", isRegister);
    elements.authLoginTab.setAttribute("aria-selected", String(!isRegister));
    elements.authRegisterTab.setAttribute("aria-selected", String(isRegister));
    elements.authFormTitle.textContent = isRegister
      ? "Tạo không gian của bạn"
      : "Chào mừng trở lại";
    elements.authFormDescription.textContent = isRegister
      ? "Đăng ký để lưu CV, hội thoại và kết quả phân tích."
      : "Đăng nhập để tiếp tục không gian nghề nghiệp của bạn.";
    showError("");

    const input = isRegister
      ? elements.registerEmail
      : elements.loginEmail;
    input?.focus();
  }

  function showAuthScreen(message = "") {
    elements.appLoading.hidden = true;
    elements.appShell.hidden = true;
    elements.authScreen.hidden = false;

    let storedMessage = "";
    try {
      storedMessage = sessionStorage.getItem(
        "multi-agent-job-assistant-auth-message",
      ) ?? "";
      sessionStorage.removeItem(
        "multi-agent-job-assistant-auth-message",
      );
    } catch {}

    showError(message || storedMessage);
    elements.loginEmail?.focus();
  }

  function showWorkspace(user) {
    const email = user?.email ?? "";
    elements.appLoading.hidden = true;
    elements.authScreen.hidden = true;
    elements.appShell.hidden = false;
    elements.currentUserEmail.textContent = email;
    elements.currentUserEmail.title = email;
    if (elements.currentUserAvatar) {
      elements.currentUserAvatar.textContent = getAvatarLabel(email);
    }
  }

  function showError(message) {
    if (!elements.authError) return;
    elements.authError.textContent = message;
    elements.authError.hidden = !message;
  }

  function setSubmitting(form, submitting) {
    isSubmitting = submitting;
    const button = form.querySelector(".auth-submit");
    const controls = form.querySelectorAll("input, button");
    controls.forEach((control) => {
      control.disabled = submitting;
    });
    button?.setAttribute("aria-busy", String(submitting));
  }

  return {
    bindEvents,
    restoreSession,
    showWorkspace,
  };
}

function getAvatarLabel(email) {
  const name = email.split("@")[0] || "U";
  const parts = name.split(/[._-]+/).filter(Boolean);
  return parts.slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

function getFriendlyAuthError(error) {
  const code = error?.details?.error?.code;

  if (error?.status === 401) {
    return "Email hoặc mật khẩu không chính xác.";
  }

  if (code === "EMAIL_ALREADY_REGISTERED") {
    return "Email này đã được đăng ký. Hãy chuyển sang đăng nhập.";
  }

  if (error?.status === 422) {
    return "Thông tin chưa hợp lệ. Mật khẩu cần có ít nhất 12 ký tự.";
  }

  return error?.message || "Không thể hoàn tất yêu cầu. Vui lòng thử lại.";
}
