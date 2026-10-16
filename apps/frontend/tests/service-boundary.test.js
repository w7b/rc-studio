import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { test } from 'node:test';

const sourceRoot = new URL('../src/', import.meta.url);

test('application and feature code delegate network access and endpoint ownership to services', () => {
  const violations = [];
  for (const path of readdirSync(sourceRoot, { recursive: true })) {
    const name = path.replaceAll('\\', '/');
    if (!/\.(js|jsx)$/.test(name) || name.startsWith('services/')) continue;
    const source = readFileSync(new URL(name, sourceRoot), 'utf8');
    const rules = [
      [/\bfetch\s*\(/, 'direct fetch'],
      [/\b(?:XMLHttpRequest|WebSocket|EventSource)\b/, 'direct network transport'],
      [/\b(?:axios\s*[.(]|sendBeacon\s*\()/, 'direct network client'],
      [/from\s+['"][^'"]*(?:shared\/api|services\/http)[^'"]*['"]/, 'transport import'],
      [/['"`]\/api\//, 'endpoint outside services'],
    ];
    for (const [pattern, reason] of rules) {
      if (pattern.test(source)) violations.push(`${name}: ${reason}`);
    }
  }
  assert.deepEqual(violations, [], 'Put requests and API URL builders in src/services.');
});
