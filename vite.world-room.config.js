import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  root: 'world-room',
  plugins: [react()],
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
