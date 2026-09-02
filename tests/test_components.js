/**
 * ZASI Frontend Structural Component Verification
 */
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const appTsxPath = path.join(__dirname, '../web/static/app.tsx');
const appJsxPath = path.join(__dirname, '../web/static/app.jsx');
const appTsx = fs.readFileSync(appTsxPath, 'utf8');
const appJsx = fs.readFileSync(appJsxPath, 'utf8');
const content = `${appTsx}\n${appJsx}`;
const packageJson = JSON.parse(fs.readFileSync(path.join(__dirname, '../package.json'), 'utf8'));
const makefile = fs.readFileSync(path.join(__dirname, '../Makefile'), 'utf8');

console.log('[*] Testing React 19 + React Router v7 TypeScript entrypoint and component declarations...');

assert(packageJson.dependencies.react.startsWith('19.'), 'package must pin React 19');
assert(packageJson.dependencies['react-dom'].startsWith('19.'), 'package must pin React DOM 19');
assert(packageJson.dependencies['react-router-dom'].startsWith('7.'), 'package must pin React Router 7');
assert(packageJson.devDependencies.typescript, 'package must include TypeScript tooling');
assert(makefile.includes('npm run typecheck'), 'Make targets must enforce the TypeScript check');
assert(!/^\s*rm .*\.coverage/m.test(makefile), 'Make clean must preserve the tracked coverage artifact');
assert(appTsx.includes("from './app.jsx?legacy'"), 'TypeScript entrypoint must preserve the reviewed cockpit implementation import');
assert(!appJsx.includes('createRoot('), 'compatibility module must not mount a second React root');
assert(appTsx.includes('createRoot'), 'TypeScript entrypoint must own React root creation');
const productionHtml = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
assert(productionHtml.includes('./static/app.tsx'), 'production page must load the TypeScript entrypoint');

assert(content.includes('BrowserRouter'), 'app.jsx must import and use BrowserRouter');
assert(content.includes('Routes'), 'app.jsx must declare Routes');
assert(content.includes('Route'), 'app.jsx must declare Route elements');
assert(content.includes('NavLink'), 'app.jsx must use NavLink for tab switching');
assert(content.includes('Outlet'), 'app.jsx must use Outlet for Shell nested routing');

assert(content.includes('OverviewPage'), 'app.jsx must declare OverviewPage');
assert(content.includes('JarvisPage'), 'app.jsx must declare JarvisPage');
assert(content.includes('SubsystemsPage'), 'app.jsx must declare SubsystemsPage');
assert(content.includes('CockpitPage'), 'app.jsx must declare CockpitPage');
assert(content.includes('MCPPage'), 'app.jsx must declare MCPPage');

assert(content.includes('HypergraphCanvas'), 'app.jsx must declare Three.js HypergraphCanvas');
assert(content.includes('useTelemetry'), 'app.jsx must declare useTelemetry hook');
assert(content.includes("from 'react'"), 'app.jsx must use bundled React imports');
assert(content.includes("from 'react-router-dom'"), 'app.jsx must use bundled router imports');
assert(content.includes("from 'three'"), 'app.jsx must use bundled Three.js import');
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
