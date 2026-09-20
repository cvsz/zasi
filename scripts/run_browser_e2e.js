const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

function resolveElectron() {
  try {
    return require('electron');
  } catch (error) {
    // Fresh installs intentionally use `npm ci --ignore-scripts`, so Electron's
    // runtime may not exist yet. Provision only the repository-pinned Electron
    // package instead of enabling arbitrary dependency lifecycle scripts.
    const root = path.resolve(__dirname, '..');
    const manifest = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
    const installedManifestPath = path.join(root, 'node_modules', 'electron', 'package.json');
    const installScript = path.join(root, 'node_modules', 'electron', 'install.js');
    const expectedVersion = manifest.devDependencies?.electron;

    if (!expectedVersion || !fs.existsSync(installedManifestPath) || !fs.existsSync(installScript)) {
      throw error;
    }

    const installedVersion = JSON.parse(fs.readFileSync(installedManifestPath, 'utf8')).version;
    if (installedVersion !== expectedVersion) {
      throw new Error(`Refusing to provision unpinned Electron ${installedVersion}; expected ${expectedVersion}`);
    }

    const provision = spawnSync(process.execPath, [installScript], {
      cwd: root,
      stdio: 'inherit',
    });
    if (provision.error || provision.status !== 0) {
      throw provision.error || new Error(`Pinned Electron provisioning failed with status ${provision.status}`);
    }

    return require('electron');
  }
}

const electronPath = resolveElectron();
const electronArgs = [
  '--no-sandbox',
  '--disable-gpu',
  '--disable-dev-shm-usage',
  'tests/test_browser_e2e.js',
];

const command = process.platform === 'linux' ? 'xvfb-run' : electronPath;
const args = process.platform === 'linux'
  ? ['-a', '--server-args=-screen 0 1280x1024x24', electronPath, ...electronArgs]
  : electronArgs;

const result = spawnSync(command, args, { stdio: 'inherit' });
if (result.error) {
  console.error(`ARIN browser E2E launcher failed: ${result.error.message}`);
  process.exit(1);
}
if (result.status !== 0) {
  console.error(
    `ARIN browser E2E launcher exited unsuccessfully: status=${String(result.status)} signal=${String(result.signal)}`,
  );
}
process.exit(result.status ?? 1);
