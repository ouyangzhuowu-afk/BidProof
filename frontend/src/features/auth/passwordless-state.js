// @ts-check
/** Pure input and timing rules shared by the minimal authentication view. */

/** @typedef {'email' | 'sms' | 'password'} AuthChannel */

/** @param {AuthChannel} channel @param {string} value */
export function normalizeIdentifier(channel, value) {
  const clean = value.trim();
  if (channel === 'email') return clean.replace(/\s/g, '').toLowerCase();
  if (channel === 'sms') {
    const phone = clean.replace(/[\s()-]/g, '');
    return /^1[3-9]\d{9}$/.test(phone) ? `+86${phone}` : phone;
  }
  return clean;
}

/** @param {AuthChannel} channel @param {string} value */
export function identifierError(channel, value) {
  const clean = normalizeIdentifier(channel, value);
  if (!clean) return channel === 'sms' ? '请输入手机号。' : channel === 'email' ? '请输入邮箱。' : '请输入邮箱或现有账号。';
  if (channel === 'email' && (clean.length > 254 || clean.split('@')[0].length > 64 || clean.includes('..')
    || !/^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}$/.test(clean))) return '请输入完整邮箱，例如 name@company.com。';
  if (channel === 'sms' && !/^\+[1-9]\d{7,14}$/.test(clean)) return '请输入 11 位中国大陆手机号，或带国家区号的手机号。';
  if (channel === 'password' && clean.length > 254) return '账号内容过长，请检查后重试。';
  return '';
}

/** One input accepts SMS auto-fill, full-code paste and full-width digits. */
export function normalizeCode(/** @type {string} */ value) {
  return value.replace(/[０-９]/g, (digit) => String(digit.charCodeAt(0) - 0xFF10)).replace(/\s/g, '');
}

/** @param {number} deadline @param {number} [now] */
export const remainingSeconds = (deadline, now = Date.now()) => Math.max(0, Math.ceil((deadline - now) / 1000));

/**
 * A deadline, not a decrementing counter: tab throttling cannot extend cooldown.
 * One owned timeout is stopped on navigation, close, resend and successful auth.
 * @param {(seconds: number) => void} onTick
 * @param {{now?: () => number, schedule?: typeof setTimeout, cancel?: typeof clearTimeout}} [clock]
 */
export function createCountdown(onTick, clock = {}) {
  const now = clock.now || Date.now;
  const schedule = clock.schedule || setTimeout;
  const cancel = clock.cancel || clearTimeout;
  /** @type {ReturnType<typeof setTimeout> | undefined} */
  let timer;
  let deadline = 0;
  let generation = 0;
  const stop = () => { generation += 1; if (timer !== undefined) cancel(timer); timer = undefined; };
  const start = (/** @type {number} */ seconds) => {
    stop();
    deadline = now() + Math.max(0, Number(seconds) || 0) * 1000;
    const owned = generation;
    let last = -1;
    const tick = () => {
      if (owned !== generation) return;
      timer = undefined;
      const remaining = remainingSeconds(deadline, now());
      if (remaining !== last) { last = remaining; onTick(remaining); }
      if (remaining > 0 && owned === generation) timer = schedule(tick, 250);
    };
    tick();
  };
  return { start, stop, remaining: () => remainingSeconds(deadline, now()) };
}

/** Only our known same-origin OAuth endpoints can be rendered as links. */
export function safeProviders(/** @type {unknown} */ configured) {
  if (!Array.isArray(configured)) return [];
  return configured.filter((entry) => entry && ['google', 'github'].includes(entry.id)
    && entry.url === `/api/auth/oauth/${entry.id}/start`)
    .map((entry) => ({ id: entry.id, label: entry.id === 'google' ? 'Google' : 'GitHub', url: entry.url }));
}
