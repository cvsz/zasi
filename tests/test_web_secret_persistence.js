/**
 * ARIN Task 8 Web/PWA secret-persistence regression.
 *
 * Provider/service credentials may exist only in ephemeral component state long
 * enough to authenticate. Browser persistence is limited to explicitly
 * allowlisted non-secret preferences.
 */
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const cockpit = fs.readFileSync(path.join(__dirname, '../web/static/cockpit.tsx'), 'utf8');

const storageWrites = [...cockpit.matchAll(/(?:localStorage|sessionStorage)\.setItem\(\s*['"]([^'"]+)['"]/g)]
    .map((match) => match[1]);
const allowedPersistentKeys = new Set(['zasi_theme']);

assert(
    storageWrites.every((key) => allowedPersistentKeys.has(key)),
    `Web/PWA must not persist provider/service secrets; unexpected storage keys: ${storageWrites.filter((key) => !allowedPersistentKeys.has(key)).join(', ')}`,
);
assert(!/(?:localStorage|sessionStorage)\.setItem\([^\n]*(?:api.?key|secret|token|credential|password)/i.test(cockpit),
    'Web/PWA must never write credential-like values to browser storage');
assert(!/indexedDB\s*\.\s*open\s*\(/.test(cockpit),
    'Web/PWA must not introduce an ungoverned IndexedDB persistence path for provider/service secrets');
assert(cockpit.includes('type="password"'),
    'authentication credential input must remain a password field');

console.log('[✓] ARIN Web/PWA no-secret persistence assertions passed');
