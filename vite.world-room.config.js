import { defineConfig } from 'vite';

export default defineConfig({
  root: 'world-room',
  server: {
    host: '127.0.0.1',
    port: 5174,
    proxy: {
      '/api/world-room': 'http://127.0.0.1:8090',
    },
  },
  build: {
    outDir: '../web/dist/world-room',
    emptyOutDir: true,
  },
});
