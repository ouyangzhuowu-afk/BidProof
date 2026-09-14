import { defineConfig } from 'vite';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));

/**
 * 旧版这里有一个 unindent-iife 插件，逐行去掉两个空格的缩进。
 * 它唯一的作用是让产物 diff 看起来短一点，但代价是任何模板字符串里的
 * 前导空格都会被吃掉——多行 HTML 模板（loadSessions 那一段）已经受影响。
 * 产物本来就是构建输出、不该进人工 review，所以这个插件去掉。
 */
export default defineConfig({
  resolve: {
    alias: {
      '@': resolve(root, 'src'),
      '@core': resolve(root, 'src/core'),
      '@ui': resolve(root, 'src/ui'),
      '@features': resolve(root, 'src/features'),
    },
  },
  esbuild: {
    // 保留可读的函数名：线上错误栈是排障的唯一线索，这个体积代价值得。
    minifyIdentifiers: false,
    legalComments: 'none',
  },
  build: {
    // 目标对齐企业内网常见浏览器：Chrome 111 起支持 CSS @layer / color-mix，
    // 与 tokens.css 的用法一致。
    target: ['chrome111', 'edge111', 'firefox113', 'safari16.4'],
    emptyOutDir: false,
    minify: 'esbuild',
    // 打开 sourcemap：旧版关闭后，线上 app.js 的报错完全无法定位。
    // 若不希望对外暴露源码，改为 'hidden' 并只上传给监控系统。
    sourcemap: true,
    cssCodeSplit: false,
    lib: {
      entry: resolve(root, 'src/main.js'),
      name: 'BidProofApp',
      formats: ['iife'],
      fileName: () => 'app.js',
    },
    outDir: resolve(root, '../static'),
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
        entryFileNames: 'app.js',
        // 防呆：lib 模式下若有人从 JS 里 import CSS，产物会叫 style.css，
        // 正好覆盖线上服役中的样式表。显式改名，让事故变成可见的多余文件。
        assetFileNames: 'app.bundled.[ext]',
      },
    },
  },
});
