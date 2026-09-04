const dictionaries = {
  zh: {
    emptyRuns: '还没有扫描任务。按三步开始：① 新建扫描 ② 上传招标文件 ③ 在作业页查看进度。',
    emptyFiltered: '没有符合当前筛选的任务，请调整条件或清除筛选。',
    trySample: '用一份招标文件试跑',
    themeDark: '深色模式',
    themeLight: '浅色模式',
  },
  en: {
    emptyRuns: 'No scans yet. Three steps: 1) New scan 2) Upload a tender 3) Watch job progress.',
    emptyFiltered: 'No tasks match the current filters. Adjust or clear filters.',
    trySample: 'Try with a sample tender',
    themeDark: 'Dark mode',
    themeLight: 'Light mode',
  },
};

export function currentLang() {
  return localStorage.getItem('bidproof-lang') === 'en' ? 'en' : 'zh';
}

export function t(key) {
  const table = dictionaries[currentLang()] || dictionaries.zh;
  return table[key] || dictionaries.zh[key] || key;
}

export function setLang(lang) {
  localStorage.setItem('bidproof-lang', lang === 'en' ? 'en' : 'zh');
  document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN';
}

export function currentTheme() {
  return localStorage.getItem('bidproof-theme') === 'dark' ? 'dark' : 'light';
}

export function applyTheme() {
  const theme = currentTheme();
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', theme === 'dark' ? '#101820' : '#eef1f5');
}

export function toggleTheme() {
  localStorage.setItem('bidproof-theme', currentTheme() === 'dark' ? 'light' : 'dark');
  applyTheme();
}
