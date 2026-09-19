const fs = require('fs');
const path = require('path');
const assert = require('assert');

const root = path.resolve(__dirname, '..');
const cockpit = fs.readFileSync(path.join(root, 'web/static/cockpit.tsx'), 'utf8');
const style = fs.readFileSync(path.join(root, 'web/static/style.css'), 'utf8');

// Keep the bounded cockpit usable from narrow/mobile viewports without adding runtime authority.
assert(/@media\s*\(max-width:\s*768px\)/.test(style), 'cockpit must retain a tablet/mobile breakpoint');
assert(/@media\s*\(max-width:\s*520px\)/.test(style), 'cockpit must retain a narrow-mobile breakpoint');
assert(/\.chat-input-row\s*\{[^}]*flex-direction:\s*column/s.test(style), 'narrow chat controls must stack instead of overflowing');
assert(/\.data-table\s*\{[^}]*font-size:/s.test(style), 'narrow data tables must have a responsive treatment');

// Guard the existing semantic landmarks and accessible names used by the governed cockpit.
assert(cockpit.includes('aria-label="Primary navigation"'), 'primary navigation must keep an accessible name');
assert(cockpit.includes('role="log"'), 'conversation stream must remain an accessible log landmark');
assert(cockpit.includes('aria-label="Search governed views"'), 'command palette search must keep an accessible name');
assert(cockpit.includes('role="img" aria-label="Capability registry visualization"'), 'capability visualization must expose a text alternative');
assert(cockpit.includes('aria-busy={!connectors}'), 'async connector status must expose its loading state');

// Keyboard focus must remain visibly represented; do not accept mouse-only affordances.
assert(/:focus/.test(style), 'interactive controls must retain visible focus styling');

console.log('ARIN responsive/accessibility contract checks passed');
