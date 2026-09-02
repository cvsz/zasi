import { defineConfig } from 'vite';

const configuredBasePath = (process.env.VITE_BASE_PATH || './').trim();
if (
  !configuredBasePath ||
  (configuredBasePath !== './' && !configuredBasePath.startsWith('/'))
) {
  throw new Error('VITE_BASE_PATH must be ./ or an absolute path prefix');
}
const assetBasePath = configuredBasePath.endsWith('/')
  ? configuredBasePath
  : `${configuredBasePath}/`;

function apiOriginCspPlugin() {
  return {
    name: 'zasi-api-origin-csp',
    transformIndexHtml(html) {
      const configuredOrigin = (process.env.VITE_API_ROOT || '').trim().replace(/\/$/, '');
      if (!configuredOrigin) return html;
      let parsedOrigin;
      try {
        parsedOrigin = new URL(configuredOrigin);
      } catch {
        throw new Error('VITE_API_ROOT must be an absolute HTTP(S) origin');
      }
      if (!['http:', 'https:'].includes(parsedOrigin.protocol) || parsedOrigin.pathname !== '/' || parsedOrigin.search || parsedOrigin.hash) {
        throw new Error('VITE_API_ROOT must be an absolute HTTP(S) origin');
      }
      return html.replace(
        "connect-src 'self';",
        `connect-src 'self' ${parsedOrigin.origin};`,
      );
    },
  };
}

export default defineConfig({
  root: 'web',
  base: assetBasePath,
  plugins: [apiOriginCspPlugin()],
  build: {
    outDir: '../web/dist',
    emptyOutDir: true,
    rollupOptions: {
      input: 'web/index.html'
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8080'
    }
  }
});
