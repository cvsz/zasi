const { spawnSync } = require('child_process');
const electronPath = require('electron');

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
process.exit(result.status ?? 1);
