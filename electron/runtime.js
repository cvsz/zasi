const fs = require('fs');
const path = require('path');
const { runtimeExecutablePath } = require('./packaging');

function runtimeError(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

function hasBundledApp(appRoot) {
  return ['backend', 'src', 'web/dist/index.html'].every((relativePath) => {
    try {
      return relativePath.endsWith('.html')
        ? fs.statSync(path.join(appRoot, relativePath)).isFile()
        : fs.statSync(path.join(appRoot, relativePath)).isDirectory();
    } catch {
      return false;
    }
  });
}

function isRegularFile(filePath) {
  try {
    return fs.statSync(filePath).isFile();
  } catch {
    return false;
  }
}

function resolveBackendLaunch({
  packaged = false,
  platform = process.platform,
  resourcesPath = process.resourcesPath,
  sourceRoot = path.resolve(__dirname, '..'),
  env = process.env,
} = {}) {
  const launchEnv = { ...env };
  if (!packaged) {
    const configuredPython = typeof env.ZASI_PYTHON === 'string' ? env.ZASI_PYTHON.trim() : '';
    return {
      command: configuredPython || 'python3',
      args: ['-m', 'backend.app'],
      cwd: sourceRoot,
      env: launchEnv,
    };
  }

  if (!resourcesPath) {
    throw runtimeError(
      'PACKAGED_RUNTIME_UNAVAILABLE',
      'Packaged Electron startup requires an explicit resources directory.',
    );
  }
  const runtimeRoot = path.join(resourcesPath, 'backend-runtimes');
  const command = runtimeExecutablePath(runtimeRoot, platform);
  const platformRoot = path.join(runtimeRoot, platform);
  if (!command || !isRegularFile(path.join(platformRoot, 'pyvenv.cfg'))) {
    throw runtimeError(
      'PACKAGED_RUNTIME_UNAVAILABLE',
      `No runnable bundled Python runtime is present for ${platform}.`,
    );
  }

  const appRoot = path.join(resourcesPath, 'zasi-app');
  if (!hasBundledApp(appRoot)) {
    throw runtimeError(
      'PACKAGED_APP_UNAVAILABLE',
      'The packaged backend source and frontend bundle are incomplete.',
    );
  }
  delete launchEnv.PYTHONHOME;
  delete launchEnv.PYTHONPATH;
  delete launchEnv.VIRTUAL_ENV;
  return {
    command,
    args: ['-m', 'backend.app'],
    cwd: appRoot,
    env: {
      ...launchEnv,
      PYTHONPATH: appRoot,
    },
  };
}

module.exports = { resolveBackendLaunch };
