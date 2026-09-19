const assert = require('assert');
const path = require('path');
const { app, BrowserWindow } = require('electron');

async function run() {
  await app.whenReady();

  const window = new BrowserWindow({
    show: false,
    width: 390,
    height: 844,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  try {
    await window.loadFile(path.resolve(__dirname, '../web/dist/index.html'));

    const evidence = await window.webContents.executeJavaScript(`(() => {
      const primaryNav = document.querySelector('[aria-label="Primary navigation"]');
      const conversationLog = document.querySelector('[role="log"]');
      const search = document.querySelector('[aria-label="Search governed views"]');
      const visualization = document.querySelector('[role="img"][aria-label="Capability registry visualization"]');
      const interactive = document.querySelector('button, a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
      if (interactive) interactive.focus();
      const focused = document.activeElement === interactive;
      const focusStyle = interactive ? getComputedStyle(interactive) : null;
      const hasVisibleFocus = !!focusStyle && (
        focusStyle.outlineStyle !== 'none' ||
        focusStyle.boxShadow !== 'none'
      );
      return {
        width: innerWidth,
        primaryNav: !!primaryNav,
        conversationLog: !!conversationLog,
        search: !!search,
        visualization: !!visualization,
        focused,
        hasVisibleFocus,
        horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      };
    })()`);

    assert.strictEqual(evidence.width, 390, 'browser must execute at the narrow mobile viewport');
    assert.strictEqual(evidence.primaryNav, true, 'primary navigation must render with an accessible name');
    assert.strictEqual(evidence.conversationLog, true, 'conversation log landmark must render');
    assert.strictEqual(evidence.search, true, 'governed-view search must render with an accessible name');
    assert.strictEqual(evidence.visualization, true, 'capability visualization must expose its text alternative');
    assert.strictEqual(evidence.focused, true, 'keyboard-focusable content must accept focus');
    assert.strictEqual(evidence.hasVisibleFocus, true, 'focused content must expose a visible focus treatment');
    assert.strictEqual(evidence.horizontalOverflow, false, 'narrow viewport must not introduce page-level horizontal overflow');

    console.log('ARIN Chromium browser E2E contract checks passed');
  } finally {
    window.destroy();
    await app.quit();
  }
}

run().catch(async (error) => {
  console.error(error);
  try { await app.quit(); } catch {}
  process.exitCode = 1;
});
