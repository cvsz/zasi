const assert = require('assert');
const fs = require('fs');
const Module = require('module');
const os = require('os');
const path = require('path');

const originalLoad = Module._load;
const spawned = [];
Module._load = function load(request, parent, isMain) {
  if (request === 'electron') {
    return {
      app: { isPackaged: true },
      BrowserWindow: class BrowserWindow {},
    };
  }
  if (request === 'child_process') {
    return {
      spawn(command, args, options) {
        const child = {
          stdout: { on() {} },
          stderr: { on() {} },
          exitCode: null,
          signalCode: null,
          on() {},
          kill() {},
        };
        spawned.push({ command, args, options });
        return child;
      },
    };
  }
  return originalLoad.call(this, request, parent, isMain);
};

let main;
try {
  main = require('../electron/main');
} finally {
  Module._load = originalLoad;
}

assert.strictEqual(typeof main.startBackend, 'function');
const previousApiKey = process.env.ZASI_API_KEY;
process.env.ZASI_API_KEY = 'electron-test-key';
try {
  assert.throws(
    () => main.startBackend({ resourcesPath: '/tmp/zasi-no-bundled-runtime' }),
    (error) => error && error.code === 'PACKAGED_RUNTIME_UNAVAILABLE',
  );

  const resourcesPath = fs.mkdtempSync(path.join(os.tmpdir(), 'zasi-electron-integrated-'));
  const runtimeRoot = path.join(resourcesPath, 'backend-runtimes', 'linux');
  fs.mkdirSync(path.join(runtimeRoot, 'bin'), { recursive: true });
  fs.mkdirSync(path.join(runtimeRoot, 'bundled'));
  fs.writeFileSync(path.join(runtimeRoot, 'bin', 'python3'), '#!/bin/sh\nexit 0\n', { mode: 0o755 });
  fs.writeFileSync(path.join(runtimeRoot, 'pyvenv.cfg'), 'home = .\n');
  for (const directory of ['backend', 'src', 'web/dist']) {
    fs.mkdirSync(path.join(resourcesPath, 'zasi-app', directory), { recursive: true });
  }
  fs.writeFileSync(path.join(resourcesPath, 'zasi-app', 'web/dist/index.html'), '<!doctype html>');
  const userDataPath = fs.mkdtempSync(path.join(os.tmpdir(), 'zasi-electron-user-data-'));
  main.startBackend({ resourcesPath, userDataPath });
  assert.strictEqual(spawned.length, 1);
  assert.strictEqual(
    spawned[0].options.env.ZASI_DATABASE_PATH,
    path.join(userDataPath, 'data', 'zasi_control_plane.db'),
  );
  assert.strictEqual(
    spawned[0].options.env.ZASI_ARTIFACT_DIRECTORY,
    path.join(userDataPath, 'artifacts'),
  );
  assert.strictEqual(spawned[0].options.cwd, path.join(resourcesPath, 'zasi-app'));
} finally {
  if (previousApiKey === undefined) delete process.env.ZASI_API_KEY;
  else process.env.ZASI_API_KEY = previousApiKey;
}
console.log('electron integration tests passed');
