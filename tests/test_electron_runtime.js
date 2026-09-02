const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { resolveBackendLaunch } = require('../electron/runtime');

function makePackagedResources() {
  const resourcesPath = fs.mkdtempSync(path.join(os.tmpdir(), 'zasi-electron-'));
  const pythonPath = path.join(resourcesPath, 'backend-runtimes', 'linux', 'bin', 'python3');
  fs.mkdirSync(path.dirname(pythonPath), { recursive: true });
  fs.writeFileSync(pythonPath, '#!/bin/sh\nexit 0\n', { mode: 0o755 });
  fs.writeFileSync(
    path.join(resourcesPath, 'backend-runtimes', 'linux', 'pyvenv.cfg'),
    'home = bundled\n',
  );
  for (const directory of ['backend', 'src', 'web/dist']) {
    fs.mkdirSync(path.join(resourcesPath, 'zasi-app', directory), { recursive: true });
  }
  fs.writeFileSync(path.join(resourcesPath, 'zasi-app', 'web/dist/index.html'), '<!doctype html>');
  return resourcesPath;
}

function testSourceCheckoutUsesConfiguredPython() {
  const launch = resolveBackendLaunch({
    packaged: false,
    sourceRoot: '/workspace/zasi',
    env: { ZASI_PYTHON: '/opt/zasi-python' },
  });
  assert.deepStrictEqual(launch, {
    command: '/opt/zasi-python',
    args: ['-m', 'backend.app'],
    cwd: '/workspace/zasi',
    env: { ZASI_PYTHON: '/opt/zasi-python' },
  });
}

function testPackagedCheckoutFailsWithoutBundledRuntime() {
  const resourcesPath = fs.mkdtempSync(path.join(os.tmpdir(), 'zasi-electron-missing-'));
  assert.throws(
    () => resolveBackendLaunch({ packaged: true, platform: 'linux', resourcesPath, env: {} }),
    (error) => error && error.code === 'PACKAGED_RUNTIME_UNAVAILABLE',
  );
}

function testPackagedCheckoutResolvesOnlyCompleteBundledResources() {
  const resourcesPath = makePackagedResources();
  const launch = resolveBackendLaunch({
    packaged: true,
    platform: 'linux',
    resourcesPath,
    env: { PYTHONPATH: '/untrusted/imports' },
  });
  assert.strictEqual(
    launch.command,
    path.join(resourcesPath, 'backend-runtimes', 'linux', 'bin', 'python3'),
  );
  assert.deepStrictEqual(launch.args, ['-m', 'backend.app']);
  assert.strictEqual(launch.cwd, path.join(resourcesPath, 'zasi-app'));
  assert.strictEqual(launch.env.PYTHONPATH, path.join(resourcesPath, 'zasi-app'));
}

function testPackagedWindowsUsesVenvScriptsPython() {
  const resourcesPath = fs.mkdtempSync(path.join(os.tmpdir(), 'zasi-electron-win-'));
  const pythonPath = path.join(resourcesPath, 'backend-runtimes', 'win32', 'Scripts', 'python.exe');
  fs.mkdirSync(path.dirname(pythonPath), { recursive: true });
  fs.writeFileSync(pythonPath, 'runtime');
  fs.writeFileSync(
    path.join(resourcesPath, 'backend-runtimes', 'win32', 'pyvenv.cfg'),
    'home = bundled\n',
  );
  for (const directory of ['backend', 'src', 'web/dist']) {
    fs.mkdirSync(path.join(resourcesPath, 'zasi-app', directory), { recursive: true });
  }
  fs.writeFileSync(path.join(resourcesPath, 'zasi-app', 'web/dist/index.html'), '<!doctype html>');

  const launch = resolveBackendLaunch({ packaged: true, platform: 'win32', resourcesPath, env: {} });
  assert.strictEqual(launch.command, pythonPath);
}

function testPackagedCheckoutRejectsAStandalonePythonExecutable() {
  const resourcesPath = makePackagedResources();
  fs.unlinkSync(path.join(resourcesPath, 'backend-runtimes', 'linux', 'pyvenv.cfg'));
  assert.throws(
    () => resolveBackendLaunch({ packaged: true, platform: 'linux', resourcesPath, env: {} }),
    (error) => error && error.code === 'PACKAGED_RUNTIME_UNAVAILABLE',
  );
}

testSourceCheckoutUsesConfiguredPython();
testPackagedCheckoutFailsWithoutBundledRuntime();
testPackagedCheckoutResolvesOnlyCompleteBundledResources();
testPackagedWindowsUsesVenvScriptsPython();
testPackagedCheckoutRejectsAStandalonePythonExecutable();
console.log('electron runtime tests passed');
