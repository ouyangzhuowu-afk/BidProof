import { defineConfig } from 'vite';
import { resolve } from 'node:path';

function unindentIife() {
  return {
    name: 'unindent-iife',
    generateBundle(_options, bundle) {
      for (const chunk of Object.values(bundle)) {
        if (chunk.type !== 'chunk') continue;
        chunk.code = chunk.code
          .split('\n')
          .map((line) => (line.startsWith('  ') ? line.slice(2) : line))
          .join('\n');
      }
    },
  };
}

export default defineConfig({
  plugins: [unindentIife()],
  build: {
    emptyOutDir: false,
    minify: false,
    sourcemap: false,
    lib: {
      entry: resolve(__dirname, 'src/app.js'),
      name: 'BidProofApp',
      formats: ['iife'],
      fileName: () => 'app.js',
    },
    outDir: resolve(__dirname, '../static'),
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
        entryFileNames: 'app.js',
      },
    },
  },
});
