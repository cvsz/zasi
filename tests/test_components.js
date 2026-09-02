/**
 * ZASI Frontend Structural Component Verification
 */
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const appJsxPath = path.join(__dirname, '../web/static/app.jsx');
const content = fs.readFileSync(appJsxPath, 'utf8');

console.log('[*] Testing React 18 + React Router v6 component declarations...');

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
assert(!fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8').includes('unpkg.com'), 'production page must not load CDN runtime dependencies');
assert(!fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8').includes('cdnjs.cloudflare.com'), 'production page must not load CDN runtime dependencies');
assert(!fs.readFileSync(path.join(__dirname, '../web/static/app.js'), 'utf8').includes('innerHTML'), 'legacy dashboard must remain inert');

console.log('[✓] All React Router v6 component assertions passed successfully!');
