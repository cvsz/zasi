const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');
const { applyPackagedStateDefaults, resolveBackendLaunch } = require('./runtime');

const BACKEND_ORIGIN = 'http://127.0.0.1:8080';
const READY_PATH = '/health/ready';
const READY_TIMEOUT_MS = 15000;
let mainWindow;
let pythonProcess;
let backendLifecycle;

function redactedLine(value) {
  return String(value)
    .replace(/(authorization|api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+/gi, '$1=[redacted]')
    .slice(0, 1000);
}

function startBackend(runtimeOptions = {}) {
  if (!process.env.ZASI_API_KEY || !process.env.ZASI_API_KEY.trim()) {
    throw new Error('ZASI_API_KEY is required before starting the Electron shell');
  }
  const packaged = runtimeOptions.packaged ?? app.isPackaged === true;
  const launchEnv = {
    ...process.env,
    ZASI_PROFILE: process.env.ZASI_PROFILE || 'local',
    ZASI_HOST: '127.0.0.1',
    ZASI_PORT: '8080',
    ZASI_CORS_ORIGINS: process.env.ZASI_CORS_ORIGINS || 'http://127.0.0.1:8080',
  };
  const launch = resolveBackendLaunch({
    ...runtimeOptions,
    packaged,
    env: launchEnv,
  });
  if (packaged) {
    launch.env = applyPackagedStateDefaults(
      launch.env,
      runtimeOptions.userDataPath ?? app.getPath('userData'),
    );
  }
  const child = spawn(launch.command, launch.args, {
    cwd: launch.cwd,
    env: launch.env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  pythonProcess = child;
  const lifecycle = { child, exited: false, killTimer: null };
  backendLifecycle = lifecycle;
  child.stdout.on('data', (data) => console.log(`[ZASI backend] ${redactedLine(data)}`));
  child.stderr.on('data', (data) => console.error(`[ZASI backend] ${redactedLine(data)}`));
  child.on('error', (error) => console.error(`[ZASI backend] process error: ${redactedLine(error.message)}`));
  child.on('exit', (code, signal) => {
    lifecycle.exited = true;
    if (lifecycle.killTimer) clearTimeout(lifecycle.killTimer);
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
  const lifecycle = backendLifecycle;
  const processToStop = pythonProcess;
  backendLifecycle = null;
  pythonProcess = null;
  if (!lifecycle || !processToStop || lifecycle.child !== processToStop) return;
  if (lifecycle.exited || processToStop.exitCode !== null || processToStop.signalCode !== null) return;
  try {
    processToStop.kill('SIGTERM');
  } catch {
    return;
  }
  lifecycle.killTimer = setTimeout(() => {
    if (lifecycle.exited || processToStop.exitCode !== null || processToStop.signalCode !== null) return;
    try { processToStop.kill('SIGKILL'); } catch { /* already exited */ }
  }, 3000);
  lifecycle.killTimer.unref();
}

function startElectron() {
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
}

if (require.main === module) {
  startElectron();
  app.on('before-quit', () => { app.isQuitting = true; stopBackend(); });
  app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
}

module.exports = { startBackend, startElectron };
