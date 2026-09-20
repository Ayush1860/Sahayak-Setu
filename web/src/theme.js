/* Light or dark.

   Follows the device until the person chooses, then remembers the choice.
   The choice is a per-viewer convenience, so it lives in localStorage and
   every access is guarded: private windows and blocked site data make these
   calls throw, and a theme preference is not worth a blank screen. */

const KEY = "sahayak-theme";

export function systemPrefersDark() {
  try {
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  } catch {
    return false;
  }
}

export function readStoredTheme() {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

export function storeTheme(theme) {
  try {
    if (theme) localStorage.setItem(KEY, theme);
    else localStorage.removeItem(KEY);
  } catch {
    // Nothing to do. The page still renders; the choice just will not survive.
  }
}

/* null means "whatever the device says". */
export function applyTheme(theme) {
  const root = document.documentElement;
  if (theme) root.setAttribute("data-theme", theme);
  else root.removeAttribute("data-theme");

  // Keep the browser chrome in step with the page.
  const meta = document.querySelector('meta[name="theme-color"]');
  const dark = theme === "dark" || (theme === null && systemPrefersDark());
  if (meta) meta.setAttribute("content", dark ? "#141416" : "#f7c99b");
}
