import globals from 'globals';

/**
 * 扁平配置，无框架插件，无 Prettier。
 * 规则只保留「能真正拦住 bug」的那些——风格问题交给 review，不浪费 CI 时间。
 */
export default [
  {
    ignores: [
      // These modules own the escape/innerHTML boundary.
      'src/ui/render.js',
      'src/escape.js',
      'src/core/icons.js',
      'src/main.js',
      'src/app.js',
    ],
  },
  {
    files: ['src/**/*.js', 'scripts/**/*.mjs'],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.es2023,
        ...globals.node,
      },
    },
    linterOptions: { reportUnusedDisableDirectives: 'error' },
    rules: {
      'no-restricted-properties': ['error', {
        object: 'document',
        property: 'write',
        message: '禁止 document.write。',
      }],
      'no-restricted-syntax': ['error', {
        selector: "AssignmentExpression[left.property.name='innerHTML']",
        message: '不要直接赋值 innerHTML；用 ui/render.js 的 mount()/setHtml()，它强制走转义层。',
      }, {
        selector: "CallExpression[callee.object.name='window'][callee.property.name='confirm']",
        message: '不要用 window.confirm；用 ui/confirm.js 的 confirmDanger()，保持确认体验一致。',
      }],
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      'no-implicit-globals': 'error',
      'no-var': 'error',
      'prefer-const': 'error',
      eqeqeq: ['error', 'smart'],
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      // Opus strangler still has async wrappers for future awaits — warn only during landing.
      'require-await': 'warn',
      'no-return-await': 'error',
      'no-promise-executor-return': 'warn',
    },
  },
];
