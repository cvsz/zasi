/**
 * ZASI Frontend Structural Component Verification
 */
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const appTsxPath = path.join(__dirname, '../web/static/app.tsx');
const appJsxPath = path.join(__dirname, '../web/static/app.jsx');
const cockpitTsxPath = path.join(__dirname, '../web/static/cockpit.tsx');
const appTsx = fs.readFileSync(appTsxPath, 'utf8');
const appJsx = fs.readFileSync(appJsxPath, 'utf8');
const cockpitTsx = fs.readFileSync(cockpitTsxPath, 'utf8');
const content = `${appTsx}\n${cockpitTsx}\n${appJsx}`;
const packageJson = JSON.parse(fs.readFileSync(path.join(__dirname, '../package.json'), 'utf8'));
const makefile = fs.readFileSync(path.join(__dirname, '../Makefile'), 'utf8');

console.log('[*] Testing React 19 + React Router v7 TypeScript entrypoint and component declarations...');

assert(packageJson.dependencies.react.startsWith('19.'), 'package must pin React 19');
assert(packageJson.dependencies['react-dom'].startsWith('19.'), 'package must pin React DOM 19');
assert(packageJson.dependencies['react-router-dom'].startsWith('7.'), 'package must pin React Router 7');
assert(packageJson.devDependencies.typescript, 'package must include TypeScript tooling');
assert(makefile.includes('npm run typecheck'), 'Make targets must enforce the TypeScript check');
assert(!/^\s*rm .*\.coverage/m.test(makefile), 'Make clean must preserve the tracked coverage artifact');
assert(appTsx.includes("from './cockpit'"), 'TypeScript entrypoint must import the typed cockpit implementation');
assert(!appJsx.includes('createRoot('), 'compatibility module must not mount a second React root');
assert(appJsx.includes("export { default } from './cockpit';"), 'compatibility module must re-export the typed cockpit implementation');
assert(appTsx.includes('createRoot'), 'TypeScript entrypoint must own React root creation');
const productionHtml = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
assert(productionHtml.includes('./static/app.tsx'), 'production page must load the TypeScript entrypoint');

assert(cockpitTsx.includes('BrowserRouter'), 'typed cockpit must import and use BrowserRouter');
assert(cockpitTsx.includes('Routes'), 'typed cockpit must declare Routes');
assert(cockpitTsx.includes('Route'), 'typed cockpit must declare Route elements');
assert(cockpitTsx.includes('NavLink'), 'typed cockpit must use NavLink for tab switching');
assert(cockpitTsx.includes('Outlet'), 'typed cockpit must use Outlet for Shell nested routing');

assert(cockpitTsx.includes('OverviewPage'), 'typed cockpit must declare OverviewPage');
assert(cockpitTsx.includes('JarvisPage'), 'typed cockpit must declare JarvisPage');
assert(cockpitTsx.includes('SubsystemsPage'), 'typed cockpit must declare SubsystemsPage');
assert(cockpitTsx.includes('CockpitPage'), 'typed cockpit must declare CockpitPage');
assert(cockpitTsx.includes('MCPPage'), 'typed cockpit must declare MCPPage');

assert(cockpitTsx.includes('HypergraphCanvas'), 'typed cockpit must declare Three.js HypergraphCanvas');
assert(cockpitTsx.includes('useTelemetry'), 'typed cockpit must declare useTelemetry hook');
assert(cockpitTsx.includes("from 'react'"), 'typed cockpit must use bundled React imports');
assert(cockpitTsx.includes("from 'react-router-dom'"), 'typed cockpit must use bundled router imports');
assert(cockpitTsx.includes("import('three')"), 'typed cockpit must lazy-load bundled Three.js');
assert(cockpitTsx.includes('role="log"'), 'cockpit conversation must expose a log landmark');
assert(cockpitTsx.includes('aria-label="Primary navigation"'), 'cockpit navigation must have an accessible label');
assert(cockpitTsx.includes('aria-busy={!connectors}'), 'async connector status must expose loading state');
assert(!content.includes('dangerouslySetInnerHTML'), 'app.jsx must not render untrusted HTML');
assert(!content.includes("/api/tick"), 'cockpit must not expose legacy GET mutation controls');
assert(!content.includes("/api/mutate"), 'cockpit must not expose legacy mutation controls');
assert(!content.includes("/api/rsi/upgrade"), 'cockpit must not expose legacy RSI hot swap');
const scriptSources = [...productionHtml.matchAll(/<script\b[^>]*\bsrc=["']([^"']+)["']/gi)].map((match) => match[1]);
const localOrigin = 'https://zasi.invalid';
assert(scriptSources.every((source) => new URL(source, localOrigin).origin === localOrigin), 'production page must load scripts from the local bundle only');
const legacyApi = fs.readFileSync(path.join(__dirname, '../src/api_server.py'), 'utf8');
assert(legacyApi.includes('integrity="sha384-CI3ELBVUz9XQO+97x6nwMDPosPR5XvsxW2ua7N1Xeygeh1IxtgqtCkGfQY9WWdHu"'), 'legacy CDN script must use the pinned SRI digest');
assert(!fs.readFileSync(path.join(__dirname, '../web/static/app.js'), 'utf8').includes('innerHTML'), 'legacy dashboard must remain inert');

console.log('[✓] All React Router v7 component assertions passed successfully!');
