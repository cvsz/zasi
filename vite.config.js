import { defineConfig } from 'vite';

export default defineConfig({
  root: 'web',
  build: {
    outDir: '../web/dist',
    emptyOutDir: true,
    rollupOptions: {
      input: 'web/index.html',
      external: ['three'],
      output: {
        globals: { three: 'THREE' }
      }
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8080',
      '/ws':  { target: 'ws://localhost:8080', ws: true }
    }
  }
});
