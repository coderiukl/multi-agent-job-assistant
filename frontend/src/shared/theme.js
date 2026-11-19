const THEME_STORAGE_KEY = "job-search-ai-theme";

function readStoredTheme() {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

function getEffectiveTheme() {
  const explicit = document.documentElement.dataset.theme;

  if (explicit === "light" || explicit === "dark") {
    return explicit;
  }

  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;

  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Storage may be unavailable (private mode); the choice still applies
    // for this page view.
  }
}

/**
 * Binds the header theme toggle. The initial theme is applied by an inline
 * script in index.html so that the first paint already uses it.
 */
export function bindThemeToggle(button) {
  if (!button) {
    return;
  }

  const stored = readStoredTheme();

  if (stored) {
    document.documentElement.dataset.theme = stored;
  }

  const updateLabel = () => {
    const next = getEffectiveTheme() === "dark" ? "sáng" : "tối";
    const label = `Chuyển sang giao diện ${next}`;

    button.setAttribute("aria-label", label);
    button.title = label;
  };

  button.addEventListener("click", () => {
    applyTheme(getEffectiveTheme() === "dark" ? "light" : "dark");
    updateLabel();
  });

  updateLabel();
}
