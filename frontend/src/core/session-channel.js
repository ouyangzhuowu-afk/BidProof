// @ts-check
const CHANNEL = 'bidproof-session-v1';
const CHANGED = 'session-changed';

/** Same-origin invalidation only: never send user, token, document or task data.
 * @param {() => void} onChange
 * @param {Window & typeof globalThis} [host]
 */
export function openSessionChannel(onChange, host = window) {
  /** @type {BroadcastChannel | null} */
  let channel = null;
  let disposed = false;
  const disconnect = () => {
    if (channel) { channel.onmessage = null; channel.close(); channel = null; }
  };
  const connect = () => {
    if (disposed || channel || typeof host.BroadcastChannel !== 'function') return;
    try {
      const opened = new host.BroadcastChannel(CHANNEL);
      channel = opened;
      opened.onmessage = (event) => {
        // A queued event from a closed instance must not affect the restored page.
        if (channel === opened && !disposed && event.data === CHANGED) onChange();
      };
    } catch { /* Restricted browser contexts retain the protected-request 401 fallback. */ }
  };
  /** @param {PageTransitionEvent} event */
  const resume = (event) => {
    if (!event.persisted || disposed) return;
    connect();
    // A restored page may have missed a change while its channel was closed.
    onChange();
  };
  host.addEventListener('pagehide', disconnect);
  host.addEventListener('pageshow', resume);
  connect();
  return {
    publish() {
      try { channel?.postMessage(CHANGED); }
      catch { /* Local invalidation still happens if this browser cannot broadcast. */ }
    },
    close() {
      disposed = true; disconnect();
      host.removeEventListener('pagehide', disconnect);
      host.removeEventListener('pageshow', resume);
    },
  };
}
