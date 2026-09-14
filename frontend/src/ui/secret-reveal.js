/**
 * 一次性凭据。
 *
 * 产品里有四处会产生**只回传一次、之后服务端只存哈希**的秘密：
 *
 *   邀请链接        POST /api/auth/invitations        → activation_path
 *   重置链接        POST /api/members/{id}/password-reset → reset_path
 *   API 令牌明文    POST /api/auth/tokens             → token
 *   MFA 恢复码      POST /api/auth/mfa/enroll         → recovery_codes[]
 *
 * 旧实现用了三种不同做法，其中后两处只是往一个 <span> 里塞 textContent：
 *
 *   message.textContent = `请立即保存令牌：${created.token}`;
 *   secret.textContent  = `密钥：…\n恢复码（仅显示一次）：\n${codes.join('\n')}`;
 *
 * 没有复制按钮，没有视觉强调，也没有任何机制阻止用户在保存之前点走。
 * 丢了 API 令牌只是要重建一个集成，丢了 MFA 恢复码是**账号锁死**。
 *
 * 这个组件把四处统一成一种呈现，并加了一个旧实现完全没有的东西：
 * **「我已保存」确认**。在用户按下它之前，调用方可以拒绝关闭所在面板。
 */

import { html, mount } from './render.js';
import { toastSuccess } from '../core/toast.js';

/**
 * @typedef {object} SecretHandle
 * @property {() => boolean} acknowledged 用户是否已确认保存
 * @property {() => void} clear           清空 DOM。离开视图时必须调用
 */

/**
 * 渲染一次性凭据。
 *
 * @param {Element | null} target 挂载点
 * @param {object} options
 * @param {string} options.title          例如「邀请链接」「API 令牌」
 * @param {string} [options.note]         有效期或使用说明
 * @param {string} [options.link]         可打开的链接（邀请 / 重置）
 * @param {string[]} [options.values]     纯文本秘密。多行用于 MFA 恢复码
 * @param {string} [options.filename]     提供下载时的文件名。不给则不显示下载
 * @param {() => void} [options.onAcknowledge]
 * @returns {SecretHandle}
 */
export function revealSecret(target, {
  title, note, link, values = [], filename, onAcknowledge,
}) {
  let acknowledged = false;
  if (!target) return { acknowledged: () => false, clear: () => {} };

  // 链接本身就是秘密，复制/下载时按纯文本处理，和令牌走同一条路径。
  const lines = link ? [link, ...values] : values;
  const text = lines.join('\n');

  mount(target, html`
    <section class="secret" aria-label="${title}">
      <header class="secret__head">
        <span class="chip chip--warning">仅显示一次</span>
        <strong>${title}</strong>
      </header>

      ${note ? html`<p class="secret__note">${note}</p>` : ''}

      <pre class="secret__value" tabindex="0">${text}</pre>

      <div class="secret__actions">
        <button class="btn btn--sm btn--secondary" type="button" data-secret-copy>
          <i data-lucide="copy"></i><span>${lines.length > 1 ? '全部复制' : '复制'}</span>
        </button>
        ${link
          ? html`<a class="btn btn--sm btn--ghost" href="${link}" target="_blank" rel="noopener">
                   <i data-lucide="external-link"></i><span>打开链接</span></a>`
          : ''}
        ${filename
          ? html`<button class="btn btn--sm btn--ghost" type="button" data-secret-download>
                   <i data-lucide="download"></i><span>下载</span></button>`
          : ''}
        <span class="secret__spacer"></span>
        <button class="btn btn--sm btn--primary" type="button" data-secret-ack>
          <i data-lucide="check"></i><span>我已保存</span>
        </button>
      </div>
    </section>
  `);

  target.querySelector('[data-secret-copy]')?.addEventListener('click', () => { void copy(text); });

  target.querySelector('[data-secret-download]')?.addEventListener('click', () => {
    download(text, filename);
  });

  target.querySelector('[data-secret-ack]')?.addEventListener('click', () => {
    acknowledged = true;
    const section = target.querySelector('.secret');
    section?.setAttribute('data-acknowledged', 'true');
    // 秘密本身不隐藏：用户点「我已保存」之后可能还想再核对一遍。
    // 这里只把状态标出来，真正的清除由调用方在离开时做。
    onAcknowledge?.();
  });

  return {
    acknowledged: () => acknowledged,
    clear: () => mount(target, ''),
  };
}

/**
 * 剪贴板。失败回退到 prompt —— 这是旧 showSecureLink() 里唯一值得保留的设计：
 * 非 HTTPS 或权限被拒时 navigator.clipboard 会抛错，
 * 而这时用户更需要一个能手动全选的地方，不是一句「复制失败」。
 *
 * @param {string} text
 */
async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
    toastSuccess('已复制到剪贴板。');
  } catch {
    window.prompt('自动复制失败，请手动复制以下内容', text);
  }
}

/** @param {string} text @param {string} filename */
function download(text, filename) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  // 旧实现的两处下载里有一处漏了这句，每次导出都泄漏一个 blob。
  URL.revokeObjectURL(url);
}
