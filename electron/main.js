const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

const BACKEND_ORIGIN = 'http://127.0.0.1:8080';
const READY_PATH = '/health/ready';
const READY_TIMEOUT_MS = 15000;
let mainWindow;
let pythonProcess;

function redactedLine(value) {
  return String(value)
    .replace(/(authorization|api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+/gi, '$1=[redacted]')
    .slice(0, 1000);
}

function startBackend() {
  if (!process.env.ZASI_API_KEY || !process.env.ZASI_API_KEY.trim()) {
    throw new Error('ZASI_API_KEY is required before starting the Electron shell');
  }
  const repoRoot = path.join(__dirname, '..');
  pythonProcess = spawn('python3', ['-m', 'backend.app'], {
    cwd: repoRoot,
    env: {
      ...process.env,
      ZASI_PROFILE: process.env.ZASI_PROFILE || 'local',
      ZASI_HOST: '127.0.0.1',
      ZASI_PORT: '8080',
      ZASI_CORS_ORIGINS: process.env.ZASI_CORS_ORIGINS || 'http://127.0.0.1:8080',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  pythonProcess.stdout.on('data', (data) => console.log(`[ZASI backend] ${redactedLine(data)}`));
  pythonProcess.stderr.on('data', (data) => console.error(`[ZASI backend] ${redactedLine(data)}`));
  pythonProcess.on('error', (error) => console.error(`[ZASI backend] process error: ${redactedLine(error.message)}`));
  pythonProcess.on('exit', (code, signal) => {
    if (code !== 0 && !app.isQuitting) console.error(`[ZASI backend] exited (${code ?? 'null'}, ${signal ?? 'unknown'})`);
  });
}

function waitForReady() {
  const startedAt = Date.now();
  return new Promise((resolve, reject) => {
    const probe = () => {
      if (Date.now() - startedAt > READY_TIMEOUT_MS) {
        reject(new Error('authoritative backend readiness timeout'));
        return;
      }
      const request = http.get(`${BACKEND_ORIGIN}${READY_PATH}`, { timeout: 1500 }, (response) => {
        let body = '';
        response.setEncoding('utf8');
        response.on('data', (chunk) => { body += chunk; });
        response.on('end', () => {
          if (response.statusCode === 200) {
            try {
              const payload = JSON.parse(body);
              if (payload.status === 'ready') { resolve(payload); return; }
            } catch { /* retry until the authoritative response is valid */ }
          }
          setTimeout(probe, 200);
        });
      });
      request.on('error', () => setTimeout(probe, 200));
      request.on('timeout', () => request.destroy());
    };
    probe();
  });
}

function isApprovedNavigation(target) {
  try {
    const parsed = new URL(target);
    return parsed.origin === BACKEND_ORIGIN && parsed.protocol === 'http:';
  } catch {
    return false;
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    title: 'ZASI J.A.R.V.I.S. Governed Cockpit',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
    },
  });
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  mainWindow.webContents.on('will-navigate', (event, target) => {
    if (!isApprovedNavigation(target)) event.preventDefault();
  });
  mainWindow.on('closed', () => { mainWindow = null; });
  return mainWindow.loadURL(`${BACKEND_ORIGIN}/`);
}

function stopBackend() {
  if (!pythonProcess || pythonProcess.killed) return;
  pythonProcess.kill('SIGTERM');
  const processToStop = pythonProcess;
  setTimeout(() => {
    if (!processToStop.killed) processToStop.kill('SIGKILL');
  }, 3000).unref();
  pythonProcess = null;
}

app.whenReady().then(async () => {
  try {
    startBackend();
    await waitForReady();
    await createWindow();
  } catch (error) {
    console.error(`[ZASI] startup failed: ${redactedLine(error.message)}`);
    stopBackend();
    app.quit();
  }
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0 && pythonProcess) createWindow();
  });
});

app.on('before-quit', () => { app.isQuitting = true; stopBackend(); });
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
