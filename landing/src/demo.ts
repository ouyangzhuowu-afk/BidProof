import { COMPLETE_MESSAGE, DEMO_DURATION_MS, DEMO_FRAMES } from './demo-model';
import type { DemoPhase } from './demo-model';
import { emitMarketing } from './tracking';

export interface DemoOptions {
  /** Injectable platform boundaries keep timing and reduced-motion behavior testable. */
  readonly motion?: Pick<MediaQueryList, 'matches' | 'addEventListener' | 'removeEventListener'>;
  readonly schedule?: (callback: () => void, delay: number) => number;
  readonly cancel?: (id: number) => void;
}
const mounted = new WeakMap<Element, () => void>();

export function mountDemo(document: Document, options: DemoOptions = {}): () => void {
  const view = document.defaultView;
  const root = document.querySelector<HTMLElement>('[data-demo]');
  if (!view || !root) return () => {};
  mounted.get(root)?.();
  function element<T extends HTMLElement>(selector: string): T {
    const found = root?.querySelector<T>(selector);
    if (!found) throw new Error(`Missing demo element: ${selector}`);
    return found;
  }
  const controller = new view.AbortController();
  const { signal } = controller;
  const button = element<HTMLButtonElement>('[data-demo-play]');
  const buttonLabel = element('[data-demo-button-label]');
  const resultPanel = element('#demo-results');
  const resultList = element('[data-demo-results]');
  const skeleton = element('[data-demo-skeleton]');
  const status = element('[data-demo-status]');
  const summary = element('[data-demo-summary]');
  const motion = options.motion ?? view.matchMedia?.('(prefers-reduced-motion: reduce)');
  const schedule = options.schedule ?? ((callback, delay) => view.setTimeout(callback, delay));
  const cancel = options.cancel ?? ((id) => view.clearTimeout(id));
  const timers = new Set<number>();
  let phase: DemoPhase = 'ready';
  let disposed = false;
  function stopTimers(): void { timers.forEach(cancel); timers.clear(); }
  function render(): void {
    const running = phase === 'running';
    root!.dataset.phase = phase;
    resultPanel.setAttribute('aria-busy', String(running));
    resultList.hidden = running;
    skeleton.hidden = !running;
    button.disabled = false;
    button.setAttribute('aria-disabled', String(running));
    buttonLabel.textContent = running ? '正在检查示例…' : phase === 'complete' ? '再看一次' : '检查这份示例';
    summary.textContent = running ? '整理中' : '1 项待补 · 2 项待复核';
  }
  function finish(): void {
    if (disposed || phase !== 'running') return;
    stopTimers();
    phase = 'complete';
    render();
    status.textContent = COMPLETE_MESSAGE;
    emitMarketing(document, 'demo', 'complete');
  }
  function later(callback: () => void, delay: number): void {
    const id = schedule(() => {
      timers.delete(id);
      if (!disposed && phase === 'running') callback();
    }, delay);
    timers.add(id);
  }
  function play(): void {
    if (disposed || phase === 'running') return;
    // Keep the result area stable when narrow layouts wrap citation text.
    skeleton.style.minHeight = `${resultList.getBoundingClientRect().height}px`;
    phase = 'running';
    render();
    emitMarketing(document, 'demo', 'play');
    if (motion?.matches || document.hidden) { finish(); return; }
    for (const frame of DEMO_FRAMES) {
      if (frame.afterMs === 0) status.textContent = frame.message;
      else later(() => { status.textContent = frame.message; }, frame.afterMs);
    }
    later(finish, DEMO_DURATION_MS);
  }
  button.addEventListener('click', play, { signal });
  document.addEventListener('visibilitychange', () => { if (document.hidden) finish(); }, { signal });
  view.addEventListener('pagehide', finish, { signal });
  const motionChanged = (): void => { if (motion?.matches) finish(); };
  motion?.addEventListener('change', motionChanged);
  render();
  function cleanup(): void {
    if (disposed) return;
    stopTimers();
    // Leave usable static content on an unmount or HMR replacement.
    if (phase === 'running') { phase = 'ready'; render(); status.textContent = '示例结果，仍需人工复核。'; }
    disposed = true;
    button.disabled = true;
    controller.abort();
    motion?.removeEventListener('change', motionChanged);
    if (mounted.get(root!) === cleanup) mounted.delete(root!);
  }
  mounted.set(root, cleanup);
  return cleanup;
}
