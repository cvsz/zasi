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

console.log('[✓] All React Router v6 component assertions passed successfully!');
