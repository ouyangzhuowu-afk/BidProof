import './style.css';
import { mountDemo } from './demo';
import { mountTracking } from './tracking';

const cleanups: Array<() => void> = [];
try { cleanups.push(mountDemo(document)); } catch {
  const status = document.querySelector('[data-demo-status]');
  if (status) status.textContent = '当前显示静态示例，可直接开始检查。';
  document.querySelectorAll<HTMLButtonElement>('[data-demo] button').forEach((button) => { button.disabled = true; });
}
cleanups.push(mountTracking(document));
// Preserve listeners on a back/forward-cache round trip; dispose on a real departure.
window.addEventListener('pagehide', (event) => {
  if (!event.persisted) cleanups.forEach((cleanup) => cleanup());
});
if (import.meta.hot) import.meta.hot.dispose(() => cleanups.forEach((cleanup) => cleanup()));
