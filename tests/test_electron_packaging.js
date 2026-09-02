const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { resolvePackagingConfig } = require('../electron/packaging');

function makeFixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'zasi-electron-package-'));
  for (const platform of ['linux', 'darwin', 'win32']) {
    const executable = platform === 'win32'
      ? path.join(root, 'runtimes', platform, 'Scripts', 'python.exe')
      : path.join(root, 'runtimes', platform, 'bin', 'python3');
    fs.mkdirSync(path.dirname(executable), { recursive: true });
    fs.writeFileSync(executable, 'runtime', { mode: 0o755 });
    fs.writeFileSync(path.join(root, 'runtimes', platform, 'pyvenv.cfg'), 'home = bundled\n');
  }
  const appRoot = path.join(root, 'app');
  for (const directory of ['backend', 'src', 'web/dist', 'config']) {
    fs.mkdirSync(path.join(appRoot, directory), { recursive: true });
  }
  fs.writeFileSync(path.join(appRoot, 'web/dist/index.html'), '<!doctype html>');
  fs.writeFileSync(path.join(appRoot, 'main.py'), '');
  return { root, appRoot, runtimeRoot: path.join(root, 'runtimes') };
}

function testPackagingRequiresCompleteRuntimeBundles() {
  const fixture = makeFixture();
  const config = resolvePackagingConfig(fixture);
  assert.deepStrictEqual(config.files, ['electron/**/*']);
  assert.deepStrictEqual(config.extraResources[0], {
    from: fixture.runtimeRoot,
    to: 'backend-runtimes',
  });
  assert.deepStrictEqual(config.extraResources.slice(1), [
    { from: path.join(fixture.appRoot, 'backend'), to: 'zasi-app/backend' },
    { from: path.join(fixture.appRoot, 'src'), to: 'zasi-app/src' },
    { from: path.join(fixture.appRoot, 'web'), to: 'zasi-app/web' },
    { from: path.join(fixture.appRoot, 'config'), to: 'zasi-app/config' },
    { from: path.join(fixture.appRoot, 'main.py'), to: 'zasi-app/main.py' },
  ]);
}

function testPackagingFailsClosedWhenRuntimeIsMissing() {
  assert.throws(
    () => resolvePackagingConfig({ appRoot: '/workspace/zasi' }),
    (error) => error && error.code === 'ELECTRON_RUNTIME_REQUIRED',
  );
}

testPackagingRequiresCompleteRuntimeBundles();
testPackagingFailsClosedWhenRuntimeIsMissing();
console.log('electron packaging tests passed');
