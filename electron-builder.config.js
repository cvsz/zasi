const { resolvePackagingConfig } = require('./electron/packaging');

module.exports = resolvePackagingConfig({
  runtimeRoot: process.env.ZASI_ELECTRON_RUNTIME_ROOT,
  appRoot: __dirname,
});
