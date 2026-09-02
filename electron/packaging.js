const fs = require('fs');
const path = require('path');

const TARGET_PLATFORMS = ['linux', 'darwin', 'win32'];

function packagingError(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

function isFile(filePath) {
  try {
    return fs.statSync(filePath).isFile();
  } catch {
    return false;
  }
}

function isDirectory(directoryPath) {
  try {
    return fs.statSync(directoryPath).isDirectory();
  } catch {
    return false;
  }
}

function isRunnable(filePath, platform) {
  try {
    const stat = fs.statSync(filePath);
    return stat.isFile() && (platform === 'win32' || (stat.mode & 0o111) !== 0);
  } catch {
    return false;
  }
}

function runtimeExecutablePath(runtimeRoot, platform) {
  const platformRoot = path.join(runtimeRoot, platform);
  const candidates = platform === 'win32'
    ? [path.join(platformRoot, 'Scripts', 'python.exe'), path.join(platformRoot, 'python.exe')]
    : [path.join(platformRoot, 'bin', 'python3'), path.join(platformRoot, 'bin', 'python')];
  return candidates.find((candidate) => isRunnable(candidate, platform)) || null;
}

function hasBundledApp(appRoot) {
  const requiredDirectories = ['backend', 'src', 'web', 'config'];
  return requiredDirectories.every((relativePath) => isDirectory(path.join(appRoot, relativePath)))
    && isFile(path.join(appRoot, 'web', 'dist', 'index.html'))
    && isFile(path.join(appRoot, 'main.py'));
}

function resolvePackagingConfig({ runtimeRoot, appRoot = path.resolve(__dirname, '..') } = {}) {
  if (!runtimeRoot || !String(runtimeRoot).trim()) {
    throw packagingError(
      'ELECTRON_RUNTIME_REQUIRED',
      'ZASI_ELECTRON_RUNTIME_ROOT must point to real per-platform Python runtimes.',
    );
  }
  const resolvedRuntimeRoot = path.resolve(String(runtimeRoot));
  for (const platform of TARGET_PLATFORMS) {
    const executable = runtimeExecutablePath(resolvedRuntimeRoot, platform);
    if (!executable || !isFile(path.join(resolvedRuntimeRoot, platform, 'pyvenv.cfg'))) {
      throw packagingError(
        'ELECTRON_RUNTIME_INCOMPLETE',
        `The Electron runtime bundle for ${platform} is missing a runnable Python environment.`,
      );
    }
  }
  const resolvedAppRoot = path.resolve(appRoot);
  if (!hasBundledApp(resolvedAppRoot)) {
    throw packagingError(
      'ELECTRON_APP_INCOMPLETE',
      'The Electron bundle requires backend, source, config, and frontend resources.',
    );
  }
  return {
    appId: 'com.zasi.cockpit',
    productName: 'ZASI J.A.R.V.I.S.',
    directories: { output: 'dist-electron' },
    files: ['electron/**/*'],
    extraResources: [
      { from: resolvedRuntimeRoot, to: 'backend-runtimes' },
      { from: path.join(resolvedAppRoot, 'backend'), to: 'zasi-app/backend' },
      { from: path.join(resolvedAppRoot, 'src'), to: 'zasi-app/src' },
      { from: path.join(resolvedAppRoot, 'web'), to: 'zasi-app/web' },
      { from: path.join(resolvedAppRoot, 'config'), to: 'zasi-app/config' },
      { from: path.join(resolvedAppRoot, 'main.py'), to: 'zasi-app/main.py' },
    ],
    linux: { target: 'AppImage' },
    mac: { target: 'dmg' },
    win: { target: 'nsis' },
  };
}

module.exports = { resolvePackagingConfig, runtimeExecutablePath };
