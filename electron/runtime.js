const fs = require('fs');
const path = require('path');
const { isValidRuntimeBundle, runtimeExecutablePath } = require('./packaging');

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

function applyPackagedStateDefaults(env, userDataPath) {
  const launchEnv = { ...env };
  if (typeof userDataPath !== 'string' || !path.isAbsolute(userDataPath)) {
    throw runtimeError(
      'PACKAGED_STATE_PATH_INVALID',
      'Packaged Electron startup requires an absolute writable user-data directory.',
    );
  }

  for (const variable of ['ZASI_DATABASE_PATH', 'ZASI_ARTIFACT_DIRECTORY']) {
    if (Object.prototype.hasOwnProperty.call(launchEnv, variable)) {
      const value = String(launchEnv[variable]).trim();
      if (!value || !path.isAbsolute(value)) {
        throw runtimeError(
          'PACKAGED_STATE_PATH_INVALID',
          `${variable} must be an absolute path in packaged Electron mode.`,
        );
      }
      launchEnv[variable] = value;
    }
  }

  const resolvedUserDataPath = path.resolve(userDataPath);
  if (!Object.prototype.hasOwnProperty.call(launchEnv, 'ZASI_DATABASE_PATH')) {
    launchEnv.ZASI_DATABASE_PATH = path.join(
      resolvedUserDataPath,
      'data',
      'zasi_control_plane.db',
    );
  }
  if (!Object.prototype.hasOwnProperty.call(launchEnv, 'ZASI_ARTIFACT_DIRECTORY')) {
    launchEnv.ZASI_ARTIFACT_DIRECTORY = path.join(resolvedUserDataPath, 'artifacts');
  }
  return launchEnv;
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
  if (!command || !isValidRuntimeBundle(runtimeRoot, platform)) {
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

module.exports = { applyPackagedStateDefaults, resolveBackendLaunch };
