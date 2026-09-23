import './style.css';
import { mountDemo } from './demo';
import { mountTracking } from './tracking';

const cleanups: Array<() => void> = [];
try { cleanups.push(mountDemo(document)); } catch {
  const status = document.querySelector('[data-demo-status]');
  if (status) status.textContent = '交互示例暂不可用。上方静态原文仍可阅读，也可以直接进入工作台。';
  document.querySelectorAll<HTMLButtonElement>('[data-demo] button').forEach((button) => { button.disabled = true; });
}
cleanups.push(mountTracking(document));

const menu = document.querySelector<HTMLDetailsElement>('.mobile-menu');
const closeMenu = (event: Event): void => {
  if (event.target instanceof Element && event.target.closest('a') && menu) menu.open = false;
};
const escapeMenu = (event: KeyboardEvent): void => {
  if (event.key === 'Escape' && menu?.open) {
    menu.open = false;
    menu.querySelector('summary')?.focus();
  }
};
menu?.addEventListener('click', closeMenu);
document.addEventListener('keydown', escapeMenu);
cleanups.push(() => { menu?.removeEventListener('click', closeMenu); document.removeEventListener('keydown', escapeMenu); });

const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
let observer: IntersectionObserver | undefined;
function stopMotion(): void {
  observer?.disconnect();
  document.querySelectorAll('.is-revealing').forEach((element) => element.classList.remove('is-revealing'));
}
function setupMotion(): void {
  stopMotion();
  if (motion.matches || document.hidden || !('IntersectionObserver' in window)) return;
  observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.add('is-revealing');
      observer?.unobserve(entry.target);
    }
  }, { threshold: .12 });
  document.querySelectorAll('[data-reveal]').forEach((element) => observer?.observe(element));
}
// Content is visible before JavaScript, after errors, and when animation is disabled.
setupMotion();
motion.addEventListener('change', setupMotion);
document.addEventListener('visibilitychange', setupMotion);
cleanups.push(() => { stopMotion(); motion.removeEventListener('change', setupMotion); document.removeEventListener('visibilitychange', setupMotion); });
window.addEventListener('pagehide', (event) => {
  if (event.persisted) { stopMotion(); return; }
  cleanups.forEach((cleanup) => cleanup());
}, { once: true });
window.addEventListener('pageshow', (event) => { if (event.persisted) setupMotion(); });
