const assert = require('assert');
const Module = require('module');

const originalLoad = Module._load;
Module._load = function load(request, parent, isMain) {
  if (request === 'electron') {
    return {
      app: { isPackaged: true },
      BrowserWindow: class BrowserWindow {},
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
} finally {
  if (previousApiKey === undefined) delete process.env.ZASI_API_KEY;
  else process.env.ZASI_API_KEY = previousApiKey;
}
console.log('electron integration tests passed');
