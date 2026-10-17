export const PREVIEW_BOOTSTRAP = `(() => {
  const values = new Map();
  const storage = {
    get length() { return values.size; },
    clear() { values.clear(); },
    getItem(key) { return values.has(String(key)) ? values.get(String(key)) : null; },
    key(index) { return [...values.keys()][index] ?? null; },
    removeItem(key) { values.delete(String(key)); },
    setItem(key, value) { values.set(String(key), String(value)); },
  };

  try {
    Object.defineProperty(window, "localStorage", { configurable: false, value: storage });
  } catch {
    // Leave the browser's storage untouched if it cannot be safely overridden.
  }

  let failed = false;
  const showFailure = () => {
    failed = true;
    if (!document.body || document.getElementById("thought2code-preview-error")) return;
    const notice = document.createElement("div");
    notice.id = "thought2code-preview-error";
    notice.setAttribute("role", "status");
    notice.textContent = "This app encountered a script error in the preview. Review the generated JavaScript file.";
    notice.style.cssText = "position:fixed;z-index:2147483647;inset:12px 12px auto;padding:12px 16px;border:1px solid #d97706;border-radius:8px;background:#fff7ed;color:#7c2d12;font:14px/1.45 system-ui,sans-serif;box-shadow:0 4px 16px #0002";
    document.body.prepend(notice);
  };

  window.addEventListener("error", showFailure, true);
  window.addEventListener("unhandledrejection", showFailure);
  document.addEventListener("DOMContentLoaded", () => { if (failed) showFailure(); });
})();`;
