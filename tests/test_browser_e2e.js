const assert = require('assert');
const fs = require('fs');
const http = require('http');
const path = require('path');
const { app, BrowserWindow } = require('electron');

const DIST_ROOT = path.resolve(__dirname, '../web/dist');

function sendJson(response, status, payload) {
  response.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
  response.end(JSON.stringify(payload));
}

function startStaticServer() {
  const server = http.createServer((request, response) => {
    const requestPath = new URL(request.url, 'http://127.0.0.1').pathname;

    // The production cockpit is authenticated by design. Keep this E2E hermetic by
    // providing only the minimum loopback API contract required to enter the shell;
    // no production auth bypass or reusable credential is introduced.
    if (requestPath === '/api/v2/sessions' && request.method === 'POST') {
      sendJson(response, 200, { access_token: 'e2e-loopback-token', tenant_id: 'e2e-tenant', device_id: 'e2e-device' });
      return;
    }
    if (requestPath === '/api/v2/settings') {
      sendJson(response, 200, { profile: 'e2e' });
      return;
    }
    if (requestPath === '/api/v2/snapshot') {
      sendJson(response, 200, { cursor: 0, capabilities: { database: 'e2e' } });
      return;
    }
    if (requestPath === '/api/v2/capabilities') {
      sendJson(response, 200, { capabilities: [] });
      return;
    }
    if (requestPath.startsWith('/api/v2/events')) {
      sendJson(response, 200, { events: [], cursor: 0 });
      return;
    }

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

async function waitForSelector(window, selector, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const rendered = await window.webContents.executeJavaScript(
      `!!document.querySelector(${JSON.stringify(selector)})`,
    );
    if (rendered) return;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  const diagnostics = await window.webContents.executeJavaScript(`({
    readyState: document.readyState,
    title: document.title,
    bodyText: document.body?.innerText?.slice(0, 500) || '',
  })`);
  throw new Error(`cockpit did not render ${selector} before E2E timeout: ${JSON.stringify(diagnostics)}`);
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
    await waitForSelector(window, '#api-key');
    await window.webContents.executeJavaScript(`(() => {
      const input = document.querySelector('#api-key');
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setter.call(input, 'e2e-only');
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      document.querySelector('form').requestSubmit();
    })()`);
    await waitForSelector(window, '[aria-label="Primary navigation"]');
    await waitForSelector(window, '[role="img"][aria-label="Capability registry visualization"]');

    await window.webContents.executeJavaScript(`document.querySelector('[aria-label="Open command palette"]').click()`);
    await waitForSelector(window, '[aria-label="Search governed views"]');

    const overviewEvidence = await window.webContents.executeJavaScript(`(() => {
      const primaryNav = document.querySelector('[aria-label="Primary navigation"]');
      const search = document.querySelector('[aria-label="Search governed views"]');
      const visualization = document.querySelector('[role="img"][aria-label="Capability registry visualization"]');
      if (!search) throw new Error('governed-view search is unavailable for focus evidence');
      const styleSnapshot = (element) => {
        const style = getComputedStyle(element);
        return {
          outlineStyle: style.outlineStyle,
          outlineWidth: style.outlineWidth,
          outlineColor: style.outlineColor,
          boxShadow: style.boxShadow,
        };
      };
      search.blur();
      const unfocusedStyle = styleSnapshot(search);
      search.focus();
      const focused = document.activeElement === search;
      const focusedStyle = styleSnapshot(search);
      const hasFocusSpecificVisual = focused && (
        focusedStyle.outlineStyle !== unfocusedStyle.outlineStyle ||
        focusedStyle.outlineWidth !== unfocusedStyle.outlineWidth ||
        focusedStyle.outlineColor !== unfocusedStyle.outlineColor ||
        focusedStyle.boxShadow !== unfocusedStyle.boxShadow
      );
      return {
        width: innerWidth,
        primaryNav: !!primaryNav,
        search: !!search,
        visualization: !!visualization,
        focused,
        hasFocusSpecificVisual,
        horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      };
    })()`);

    assert.strictEqual(overviewEvidence.width, 390, 'browser must execute at the narrow mobile viewport');
    assert.strictEqual(overviewEvidence.primaryNav, true, 'primary navigation must render with an accessible name');
    assert.strictEqual(overviewEvidence.search, true, 'governed-view search must render with an accessible name');
    assert.strictEqual(overviewEvidence.visualization, true, 'capability visualization must expose its text alternative');
    assert.strictEqual(overviewEvidence.focused, true, 'keyboard-focusable content must accept focus');
    assert.strictEqual(overviewEvidence.hasFocusSpecificVisual, true, 'focused content must expose a focus-specific visual treatment');
    assert.strictEqual(overviewEvidence.horizontalOverflow, false, 'narrow viewport must not introduce page-level horizontal overflow');

    // Exercise the BrowserRouter through its rendered NavLink. A hard location
    // reload would discard the intentionally in-memory authenticated session and
    // test login recovery instead of the J.A.R.V.I.S. route contract.
    await window.webContents.executeJavaScript(`(() => {
      const jarvisLink = document.querySelector('a[href="/jarvis"]');
      if (!jarvisLink) throw new Error('J.A.R.V.I.S. navigation link is unavailable');
      jarvisLink.click();
    })()`);
    await waitForSelector(window, '[role="log"]');
    const conversationLog = await window.webContents.executeJavaScript(`!!document.querySelector('[role="log"]')`);
    assert.strictEqual(conversationLog, true, 'conversation log landmark must render on the J.A.R.V.I.S. route');

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
