// @ts-check
/** Storage is optional: disabled cookies/storage must not prevent boot. */
/** @type {Map<string, string | null>} */
const fallback = new Map();
/** @param {string} key @returns {string | null} */
export function readPreference(key) {
  if (fallback.has(key)) return fallback.get(key) ?? null;
  try { return localStorage.getItem(key); }
  catch { return null; }
}
/** @param {string} key @param {string | null} value */
export function writePreference(key, value) {
  fallback.set(key, value);
  try { if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value); }
  catch { /* A per-tab preference is sufficient when browser storage is disabled. */ }
}
