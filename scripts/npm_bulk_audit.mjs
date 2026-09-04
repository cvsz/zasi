#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);
const semver = require('semver');

const LEVELS = ['info', 'low', 'moderate', 'high', 'critical'];
const DEFAULT_ENDPOINT = 'https://registry.npmjs.org/-/npm/v1/security/advisories/bulk';

function boundedInteger(name, fallback, minimum, maximum) {
  const value = process.env[name] ?? String(fallback);
  if (!/^[0-9]+$/.test(value)) {
    throw new Error(`${name} must be an integer from ${minimum} through ${maximum}`);
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new Error(`${name} must be an integer from ${minimum} through ${maximum}`);
  }
  return parsed;
}

function packageNameFromLocation(location) {
  const match = location.match(/(?:^|\/)node_modules\/((?:@[^/]+\/)?[^/]+)$/);
  return match?.[1] ?? null;
}

export function buildBulkRequest(lockfile, { omitDev = true } = {}) {
  if (!lockfile || typeof lockfile.packages !== 'object' || lockfile.packages === null) {
    throw new Error('package-lock.json has no packages map; refusing to audit');
  }

  const versionsByName = new Map();
  const installed = [];
  for (const [location, entry] of Object.entries(lockfile.packages)) {
    if (!location || !entry || typeof entry.version !== 'string' || entry.link) continue;
    if (omitDev && entry.dev === true) continue;
    const name = entry.name ?? packageNameFromLocation(location);
    if (!name) throw new Error(`cannot derive package name for ${location}`);
    if (!semver.valid(entry.version)) {
      throw new Error(`invalid locked version for ${name}: ${entry.version}`);
    }
    if (!versionsByName.has(name)) versionsByName.set(name, new Set());
    versionsByName.get(name).add(entry.version);
    installed.push({ name, version: entry.version, location });
  }

  if (installed.length === 0) throw new Error('no auditable packages found in package-lock.json');
  return {
    body: Object.fromEntries(
      [...versionsByName.entries()].map(([name, versions]) => [name, [...versions].sort()]),
    ),
    installed,
  };
}

export function summarizeAudit(lockfile, auditResponse, { omitDev = true } = {}) {
  if (!auditResponse || typeof auditResponse !== 'object' || Array.isArray(auditResponse)) {
    throw new Error('bulk audit response is not an object; refusing to pass');
  }

  const { installed } = buildBulkRequest(lockfile, { omitDev });
  const counts = Object.fromEntries(LEVELS.map((level) => [level, 0]));
  const seen = new Set();

  for (const { name, version } of installed) {
    const advisories = auditResponse[name];
    if (advisories === undefined) continue;
    if (!Array.isArray(advisories)) throw new Error(`bulk audit advisories for ${name} are not an array`);

    for (const advisory of advisories) {
      if (!advisory || typeof advisory !== 'object') {
        throw new Error(`bulk audit advisory for ${name} is malformed`);
      }
      const severity = advisory.severity;
      const vulnerableVersions = advisory.vulnerable_versions;
      if (!LEVELS.includes(severity) || typeof vulnerableVersions !== 'string') {
        throw new Error(`bulk audit advisory for ${name} is missing a valid severity or version range`);
      }
      let affected;
      try {
        affected = semver.satisfies(version, vulnerableVersions, { includePrerelease: true });
      } catch (error) {
        throw new Error(`bulk audit advisory for ${name} has an invalid version range: ${error.message}`);
      }
      if (!affected) continue;

      const advisoryId = advisory.id ?? `${advisory.url ?? ''}|${advisory.title ?? ''}|${severity}|${vulnerableVersions}`;
      const findingKey = `${name}@${version}:${advisoryId}`;
      if (seen.has(findingKey)) continue;
      seen.add(findingKey);
      counts[severity] += 1;
    }
  }

  const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
  return {
    auditedPackages: installed.length,
    vulnerabilities: counts,
    total,
  };
}

function isTransient(error) {
  if (error?.transient === true) return true;
  const message = String(error?.message ?? error);
  return error?.name === 'AbortError' || /(?:ECONNRESET|ECONNREFUSED|ETIMEDOUT|EAI_AGAIN|ENOTFOUND|fetch failed|timeout)/i.test(message);
}

function retryableResponse(status) {
  return status === 408 || status === 425 || status === 429 || status >= 500;
}

export async function fetchBulkAudit(body, {
  endpoint = process.env.ZASI_NPM_AUDIT_ENDPOINT ?? DEFAULT_ENDPOINT,
  fetchImpl = globalThis.fetch,
} = {}) {
  if (typeof fetchImpl !== 'function') throw new Error('Node fetch is unavailable; refusing to audit');
  const parsedEndpoint = new URL(endpoint);
  if (parsedEndpoint.protocol !== 'https:') throw new Error('npm audit endpoint must use HTTPS');
  const attempts = boundedInteger('ZASI_NPM_AUDIT_ATTEMPTS', 3, 1, 5);
  const delaySeconds = boundedInteger('ZASI_NPM_AUDIT_RETRY_DELAY_SECONDS', 5, 0, 60);
  const timeoutMs = boundedInteger('ZASI_NPM_AUDIT_TIMEOUT_MS', 30000, 1000, 120000);

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetchImpl(endpoint, {
        method: 'POST',
        headers: {
          accept: 'application/json',
          'content-type': 'application/json',
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      const text = await response.text();
      if (!response.ok) {
        const error = new Error(`npm bulk advisory endpoint returned HTTP ${response.status}`);
        error.transient = retryableResponse(response.status);
        throw error;
      }
      let parsed;
      try {
        parsed = JSON.parse(text);
      } catch (error) {
        throw new Error(`npm bulk advisory endpoint returned invalid JSON: ${error.message}`);
      }
      return { response: parsed, attempts: attempt };
    } catch (error) {
      if (!isTransient(error) || attempt === attempts) throw error;
      console.error(`npm bulk advisory service failure (attempt ${attempt}/${attempts}); retrying.`);
      if (delaySeconds > 0) await new Promise((resolve) => setTimeout(resolve, delaySeconds * 1000));
    } finally {
      clearTimeout(timeout);
    }
  }
  throw new Error('npm bulk audit did not complete');
}

export async function main() {
  const lockPath = path.resolve(process.env.ZASI_PACKAGE_LOCK ?? 'package-lock.json');
  const lockfile = JSON.parse(await fs.readFile(lockPath, 'utf8'));
  const { body } = buildBulkRequest(lockfile, { omitDev: true });
  const { response, attempts } = await fetchBulkAudit(body);
  const summary = summarizeAudit(lockfile, response, { omitDev: true });
  console.log(JSON.stringify({ endpoint: DEFAULT_ENDPOINT, attempts, ...summary }, null, 2));
  if (summary.total !== 0) {
    throw new Error(`npm bulk audit found ${summary.total} vulnerability finding(s)`);
  }
  console.error(`npm bulk audit verified 0 vulnerabilities across ${summary.auditedPackages} production packages.`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
