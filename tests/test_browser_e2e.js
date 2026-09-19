const assert = require('assert');
const fs = require('fs');
const http = require('http');
const path = require('path');
const { app, BrowserWindow } = require('electron');

const DIST_ROOT = path.resolve(__dirname, '../web/dist');

function startStaticServer() {
  const server = http.createServer((request, response) => {
    const requestPath = new URL(request.url, 'http://127.0.0.1').pathname;
    const relativePath = requestPath === '/' ? 'index.html' : requestPath.replace(/^\/+/, '');
    const candidate = path.resolve(DIST_ROOT, relativePath);
    const relativeCandidate = path.relative(DIST_ROOT, candidate);
    if (relativeCandidate.startsWith('..') || path.isAbsolute(relativeCandidate)) {
      response.writeHead(403).end('forbidden');
      return;
    }
    fs.readFile(candidate, (error, body) => {
      if (error) {
        response.writeHead(error.code === 'ENOENT' ? 404 : 500).end('not found');
        return;
      }
      const extension = path.extname(candidate);
      const contentType = extension === '.html' ? 'text/html; charset=utf-8'
        : extension === '.js' ? 'text/javascript; charset=utf-8'
          : extension === '.css' ? 'text/css; charset=utf-8'
            : 'application/octet-stream';
      response.writeHead(200, { 'Content-Type': contentType, 'Cache-Control': 'no-store' });
      response.end(body);
    });
  });
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      resolve({ server, url: `http://127.0.0.1:${address.port}/` });
    });
  });
}

async function waitForCockpitRender(window, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const rendered = await window.webContents.executeJavaScript(
      `!!document.querySelector('[aria-label="Primary navigation"]')`,
    );
    if (rendered) return;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  const diagnostics = await window.webContents.executeJavaScript(`({
    readyState: document.readyState,
    title: document.title,
    bodyText: document.body?.innerText?.slice(0, 500) || '',
  })`);
  throw new Error(`cockpit did not render primary navigation before E2E timeout: ${JSON.stringify(diagnostics)}`);
}

async function run() {
  await app.whenReady();
  const { server, url } = await startStaticServer();

  const window = new BrowserWindow({
    show: false,
    width: 390,
    height: 844,
    useContentSize: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  window.webContents.on('render-process-gone', (_event, details) => {
    console.error('ARIN Chromium renderer exited unexpectedly', details.reason, details.exitCode);
  });

  try {
    await window.loadURL(url);
    await waitForCockpitRender(window);

    const evidence = await window.webContents.executeJavaScript(`(() => {
      const primaryNav = document.querySelector('[aria-label="Primary navigation"]');
      const conversationLog = document.querySelector('[role="log"]');
      const search = document.querySelector('[aria-label="Search governed views"]');
      const visualization = document.querySelector('[role="img"][aria-label="Capability registry visualization"]');
      const interactive = document.querySelector('button, a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
      if (interactive) interactive.focus();
      const focused = document.activeElement === interactive;
      const focusStyle = interactive ? getComputedStyle(interactive) : null;
      const hasVisibleFocus = !!focusStyle && (
        focusStyle.outlineStyle !== 'none' ||
        focusStyle.boxShadow !== 'none'
      );
      return {
        width: innerWidth,
        primaryNav: !!primaryNav,
        conversationLog: !!conversationLog,
        search: !!search,
        visualization: !!visualization,
        focused,
        hasVisibleFocus,
        horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      };
    })()`);

    assert.strictEqual(evidence.width, 390, 'browser must execute at the narrow mobile viewport');
    assert.strictEqual(evidence.primaryNav, true, 'primary navigation must render with an accessible name');
    assert.strictEqual(evidence.conversationLog, true, 'conversation log landmark must render');
    assert.strictEqual(evidence.search, true, 'governed-view search must render with an accessible name');
    assert.strictEqual(evidence.visualization, true, 'capability visualization must expose its text alternative');
    assert.strictEqual(evidence.focused, true, 'keyboard-focusable content must accept focus');
    assert.strictEqual(evidence.hasVisibleFocus, true, 'focused content must expose a visible focus treatment');
    assert.strictEqual(evidence.horizontalOverflow, false, 'narrow viewport must not introduce page-level horizontal overflow');

    console.log('ARIN Chromium browser E2E contract checks passed');
  } finally {
    if (!window.isDestroyed()) window.destroy();
    await new Promise((resolve) => server.close(resolve));
  }
}

run()
  .then(() => app.quit())
  .catch((error) => {
    console.error(error);
    app.exit(1);
  });
