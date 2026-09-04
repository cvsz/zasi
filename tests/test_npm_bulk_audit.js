const assert = require('node:assert/strict');
const test = require('node:test');
const api = import('../scripts/npm_bulk_audit.mjs');

test('bulk request contains production lockfile packages and omits dev packages', async () => {
  const { buildBulkRequest } = await api;
  const lockfile = {
    packages: {
      '': { name: 'example', version: '1.0.0' },
      'node_modules/production-package': { version: '1.2.3' },
      'node_modules/production-package/node_modules/nested-package': { version: '2.0.0' },
      'node_modules/development-package': { version: '3.0.0', dev: true },
    },
  };

  const { body, installed } = buildBulkRequest(lockfile);
  assert.deepEqual(body, {
    'nested-package': ['2.0.0'],
    'production-package': ['1.2.3'],
  });
  assert.equal(installed.length, 2);
});

test('bulk response counts only advisories affecting installed production versions', async () => {
  const { summarizeAudit } = await api;
  const lockfile = {
    packages: {
      '': { name: 'example', version: '1.0.0' },
      'node_modules/production-package': { version: '1.2.3' },
      'node_modules/development-package': { version: '3.0.0', dev: true },
    },
  };
  const response = {
    'production-package': [
      { id: 12, severity: 'high', vulnerable_versions: '<2.0.0' },
      { id: 12, severity: 'high', vulnerable_versions: '<2.0.0' },
      { id: 13, severity: 'moderate', vulnerable_versions: '<1.0.0' },
    ],
    'development-package': [
      { id: 14, severity: 'critical', vulnerable_versions: '*' },
    ],
  };

  assert.deepEqual(summarizeAudit(lockfile, response), {
    auditedPackages: 1,
    vulnerabilities: { info: 0, low: 0, moderate: 0, high: 1, critical: 0 },
    total: 1,
  });
});

test('bulk audit retries transient registry responses and returns the attempt count', async () => {
  const { fetchBulkAudit } = await api;
  const names = [
    'ZASI_NPM_AUDIT_ATTEMPTS',
    'ZASI_NPM_AUDIT_RETRY_DELAY_SECONDS',
    'ZASI_NPM_AUDIT_TIMEOUT_MS',
  ];
  const previous = Object.fromEntries(names.map((name) => [name, process.env[name]]));
  Object.assign(process.env, {
    ZASI_NPM_AUDIT_ATTEMPTS: '3',
    ZASI_NPM_AUDIT_RETRY_DELAY_SECONDS: '0',
    ZASI_NPM_AUDIT_TIMEOUT_MS: '1000',
  });

  let calls = 0;
  try {
    const result = await fetchBulkAudit({}, {
      endpoint: 'https://registry.npmjs.org/-/npm/v1/security/advisories/bulk',
      fetchImpl: async () => {
        calls += 1;
        if (calls < 3) return { ok: false, status: 503, text: async () => '' };
        return { ok: true, status: 200, text: async () => '{}' };
      },
    });
    assert.equal(result.attempts, 3);
    assert.equal(calls, 3);
    assert.deepEqual(result.response, {});
  } finally {
    for (const name of names) {
      if (previous[name] === undefined) delete process.env[name];
      else process.env[name] = previous[name];
    }
  }
});

test('malformed advisory data fails closed', async () => {
  const { summarizeAudit } = await api;
  const lockfile = {
    packages: {
      '': { name: 'example', version: '1.0.0' },
      'node_modules/production-package': { version: '1.2.3' },
    },
  };

  assert.throws(
    () => summarizeAudit(lockfile, { 'production-package': [{ severity: 'high' }] }),
    /missing a valid severity or version range/,
  );
});
