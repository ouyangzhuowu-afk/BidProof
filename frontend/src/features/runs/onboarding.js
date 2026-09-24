/** First-run progress records successful actions, scoped to the signed-in account. */
import { html, mount } from '../../ui/render.js';

const STEPS = ['选择场景', '输入一次数据', '查看交付结果'];
let accountKey = '';
let completed = 0;
let collapsed = false;
let off = () => {};

export function startOnboarding(user) {
  stopOnboarding();
  if (!user?.user_id || !user?.workspace_id || user.role === 'VIEWER') return;
  accountKey = `bidproof:onboarding:v1:${encodeURIComponent(user.workspace_id)}:${encodeURIComponent(user.user_id)}`;
  try {
    const saved = JSON.parse(localStorage.getItem(accountKey) || 'null');
    completed = Number.isInteger(saved?.completed) ? Math.max(0, Math.min(3, saved.completed)) : 0;
    collapsed = saved?.collapsed === true;
  } catch { /* Restricted storage never blocks product entry. */ }
  render();
}

export function advanceOnboarding(step) {
  if (!accountKey || !Number.isInteger(step) || step < 1 || step > 3 || step <= completed) return;
  completed = step;
  if (completed === 3) collapsed = true;
  save(); render();
}

export function stopOnboarding() {
  off(); off = () => {};
  accountKey = ''; completed = 0; collapsed = false;
  document.querySelector('#first-run-guide')?.replaceChildren();
}

function save() {
  try { localStorage.setItem(accountKey, JSON.stringify({ completed, collapsed })); } catch { /* Optional preference. */ }
}

function render() {
  const target = document.querySelector('#first-run-guide');
  if (!target) return;
  off();
  mount(target, html`<details class="first-run" ${collapsed ? '' : html`open`}>
    <summary><span>${completed === 3 ? '已完成首次体验' : '完成你的第一次检查'}</span>
      <span class="first-run__count">${completed} / 3 <span aria-hidden="true">⌄</span></span></summary>
    <ol aria-label="首次检查进度">${STEPS.map((label, i) => html`
      <li data-complete="${i < completed}" ${i === completed ? html`aria-current="step"` : ''}>
        <span class="first-run__number" aria-hidden="true">${i < completed ? '✓' : i + 1}</span>
        <span>${label}<span class="sr-only">${i < completed ? '，已完成' : i === completed ? '，当前步骤' : '，待完成'}</span></span>
      </li>`)}</ol>
  </details>`);
  const details = target.querySelector('details');
  const onToggle = () => { collapsed = !details.open; save(); };
  details.addEventListener('toggle', onToggle);
  off = () => details.removeEventListener('toggle', onToggle);
}
