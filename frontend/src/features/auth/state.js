/**
 * 鉴权状态机 —— 纯函数层。
 *
 * 这是本次重构里唯一一个**刻意做成纯函数**的模块，理由很具体：
 *
 * 旧实现的 applyAuthMode() 是 54 行，对同一个表单做了 24 处
 * hidden / required / textContent / disabled 的命令式赋值，
 * 其中 #auth-help 那一处是**四层嵌套三元**。
 *
 * 问题不是「难看」，是**无法验证**。要确认「个人注册开启 + 需要初始化令牌
 * + MFA 挂起」这个组合下界面对不对，只能在脑子里跑一遍 54 行；
 * 而 4 模式 × 2 MFA 态 × 6 布尔开关的组合空间远大于能手工检查的范围。
 *
 * 拆开之后：这个文件把 (status, mode, pendingMfa) 映射成一个视图模型，
 * 不碰 DOM、不发请求、没有副作用 —— **可以在 node 里直接断言**。
 * view.js 只负责把模型刷到 DOM 上，一行判断都不做。
 */

/** @typedef {import('../../../types/api.js').AuthStatus} AuthStatus */

/** @typedef {'setup' | 'login' | 'register' | 'trial'} AuthMode */

/**
 * 模式可达性钳制。
 *
 * 旧实现把这套判断写了两遍 —— setAuthMode() 里一遍、showAuth() 里一遍，
 * 两处不一致时以后者为准，但没有任何机制保证它们一致。
 *
 * 一条不变式：**setup_required 为真时，login 不可达**。
 * 工作区还没创建，登录没有意义。
 *
 * @param {AuthStatus | null} status
 * @param {string} requested
 * @returns {AuthMode}
 */
export function clampMode(status, requested) {
  const setupRequired = Boolean(status?.setup_required);
  const personal = Boolean(status?.personal_signup_enabled);
  // 试用加入在初始化阶段没有意义：还没有企业空间可加入。
  const trial = Boolean(status?.trial_join_enabled) && !setupRequired;

  if (setupRequired) {
    // 初始化阶段只允许 setup 与（如果开了）个人注册 —— 后者是独立工作区，
    // 不依赖企业空间是否存在。
    if (requested === 'register' && personal) return 'register';
    return 'setup';
  }
  if (requested === 'setup') return 'login';
  if (requested === 'register') return personal ? 'register' : 'login';
  if (requested === 'trial') return trial ? 'trial' : 'login';
  return 'login';
}

/**
 * 每种模式的端点。**不要在别处再写一份映射** ——
 * 旧实现把它散在 submitAuth() 的 if/else if 链里，
 * 与文案、字段可见性的判断交织在一起。
 *
 * @type {Record<AuthMode, string>}
 */
export const MODE_ENDPOINT = {
  setup: 'bootstrap',
  login: 'login',
  register: 'register',
  trial: 'trialJoin',
};

/**
 * 把表单值组装成请求体。
 *
 * 契约要点（逐条核对过旧实现，改动即改对外契约）：
 *   setup     另需 workspace_name、bootstrap_token（可为 null）
 *   trial     另需 join_code
 *   register  display_name 可选，**空字符串不要发** —— 后端会当成一个合法的空名字
 *
 * @param {AuthMode} mode
 * @param {Record<string, string>} fields
 * @returns {Record<string, unknown>}
 */
export function buildPayload(mode, fields) {
  const payload = {
    username: (fields.username || '').trim(),
    password: fields.password || '',
  };
  if (mode === 'setup') {
    payload.workspace_name = (fields.workspace || '').trim();
    payload.bootstrap_token = fields.bootstrapToken || null;
  }
  if (mode === 'trial') {
    payload.join_code = fields.joinCode || '';
  }
  if (mode === 'register') {
    const displayName = (fields.displayName || '').trim();
    if (displayName) payload.display_name = displayName;
  }
  return payload;
}

/**
 * 需要确认密码的模式。这三种都在**创建新凭据**，
 * 输错一个字符就是一个再也登不进去的账号。
 *
 * @param {AuthMode} mode
 */
export function needsConfirm(mode) {
  return mode === 'setup' || mode === 'trial' || mode === 'register';
}

/**
 * 视图模型。渲染层照着它刷 DOM，不做任何判断。
 *
 * @typedef {object} AuthView
 * @property {AuthMode} mode
 * @property {boolean} pendingMfa
 * @property {string} title
 * @property {string} subtitle
 * @property {string} submitLabel
 * @property {string} loadingLabel
 * @property {string} helpText
 * @property {boolean} helpVisible
 * @property {boolean} submitDisabled
 * @property {string} focus                 选择器
 * @property {boolean} modeSwitcherVisible
 * @property {Record<string, boolean>} modeButtons
 * @property {Record<string, boolean>} visible
 * @property {Record<string, boolean>} required
 * @property {boolean} credentialsDisabled  MFA 挂起时锁住用户名与密码
 * @property {number} passwordMinLength
 * @property {string} passwordAutocomplete
 */

/**
 * 把三个输入解析成一个完整的视图模型。
 *
 * @param {AuthStatus | null} status
 * @param {string} requestedMode
 * @param {boolean} pendingMfa
 * @returns {AuthView}
 */
export function resolveAuthView(status, requestedMode, pendingMfa) {
  const mode = clampMode(status, requestedMode);
  const setupRequired = Boolean(status?.setup_required);
  const personal = Boolean(status?.personal_signup_enabled);
  const trial = Boolean(status?.trial_join_enabled) && !setupRequired;
  const tokenRequired = mode === 'setup' && Boolean(status?.bootstrap_token_required);
  // 生产环境未配置初始化令牌时，bootstrap 一定失败，提前禁用提交。
  const locked = mode === 'setup' && Boolean(status?.bootstrap_locked);
  const confirm = needsConfirm(mode);

  return {
    mode,
    pendingMfa,

    title: pendingMfa ? '二次验证' : TITLES[mode],
    subtitle: pendingMfa
      ? '打开身份验证器应用读取验证码，或输入一次性恢复码。'
      : SUBTITLES[mode],

    submitLabel: pendingMfa ? '完成验证' : SUBMIT_LABELS[mode],
    loadingLabel: pendingMfa ? '正在验证' : LOADING_LABELS[mode],

    helpText: helpFor(mode, personal, trial),
    helpVisible: mode !== 'setup' && !pendingMfa,

    // 只有 bootstrap 被锁才禁用提交。
    // **旧实现在 MFA 挂起时也把提交按钮 disabled 了**，
    // 而验证码正是通过同一个表单提交的 —— 用户只能靠在输入框里按回车，
    // 点按钮没有任何反应。这是个真 bug。
    submitDisabled: locked,

    focus: pendingMfa ? '#auth-mfa-code' : FOCUS[mode],

    // 只有一种模式可选时不显示切换器：一个孤零零的按钮只会让人困惑。
    modeSwitcherVisible: !pendingMfa && (personal || trial || setupRequired),
    modeButtons: {
      setup: setupRequired,
      login: !setupRequired,
      register: personal,
      trial,
    },

    visible: {
      setupFields: mode === 'setup',
      bootstrapToken: tokenRequired,
      trialFields: mode === 'trial',
      registerFields: mode === 'register',
      confirmField: confirm,
      passwordHint: confirm,
      mfaFields: pendingMfa,
      // OIDC 只在纯登录态出现：其余模式都在创建账号，走不通企业身份源。
      oidc: mode === 'login' && !pendingMfa && Boolean(status?.oidc_enabled),
    },

    required: {
      workspace: mode === 'setup',
      bootstrapToken: tokenRequired,
      joinCode: mode === 'trial',
      confirm,
      mfaCode: pendingMfa,
    },

    credentialsDisabled: pendingMfa,
    passwordMinLength: confirm ? 8 : 1,
    passwordAutocomplete: confirm ? 'new-password' : 'current-password',
  };
}

/* ── 文案表 ──────────────────────────────────────────────────────────────
   全部集中在这里。旧实现把它们内联成四层嵌套三元，
   改一句文案要先看懂整个条件链。
   ───────────────────────────────────────────────────────────────────── */

/** @type {Record<AuthMode, string>} */
const TITLES = {
  setup: '初始化企业管理员',
  login: '登录工作台',
  register: '注册个人账号',
  trial: '试用加入企业空间',
};

/** @type {Record<AuthMode, string>} */
const SUBTITLES = {
  setup: '使用运维令牌创建首个企业空间和所有者账号。',
  login: '使用个人或企业账号进入任务与证据数据。',
  register: '自行创建个人工作区，与企业空间隔离，注册后即可登录使用。',
  trial: '输入组织者提供的试用加入码，自助创建复核人账号。',
};

/** @type {Record<AuthMode, string>} */
const SUBMIT_LABELS = {
  setup: '创建并进入',
  login: '登录',
  register: '注册并进入',
  trial: '加入并进入',
};

/** @type {Record<AuthMode, string>} */
const LOADING_LABELS = {
  setup: '正在初始化',
  login: '正在登录',
  register: '正在注册',
  trial: '正在加入',
};

/** @type {Record<AuthMode, string>} */
const FOCUS = {
  setup: '#auth-workspace',
  login: '#auth-username',
  register: '#auth-username',
  trial: '#auth-join-code',
};

/**
 * 帮助文案。这是旧实现里那处四层嵌套三元，展开成三个 if。
 *
 * @param {AuthMode} mode @param {boolean} personal @param {boolean} trial
 */
function helpFor(mode, personal, trial) {
  if (mode === 'register') return '已有账号？切换到「登录」。企业成员也可由管理员邀请加入。';
  if (mode === 'trial') return '已有账号？切换到「登录」。忘记密码仍需管理员重置。';
  if (personal) return '没有账号？切换到「个人注册」。企业成员也可使用试用加入码或联系管理员。';
  if (trial) return '没有账号？切换到「试用加入」。无法登录可联系管理员重置密码。';
  return '无法登录？请联系企业管理员生成一次性密码重置链接。';
}
