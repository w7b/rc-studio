import assert from 'node:assert/strict';
import { test } from 'node:test';
import { navigateRoute } from '../src/shared/hooks/useRoute.js';

function browserAt(t, path) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'window');
  const browser = new EventTarget();
  const calls = { history: [], scroll: [], navigation: [] };
  browser.location = new URL(path, 'https://studio.example');
  browser.history = Object.fromEntries(
    ['pushState', 'replaceState'].map((method) => [
      method,
      (_state, _title, target) => {
        browser.location = new URL(target, browser.location);
        calls.history.push(method);
      },
    ])
  );
  browser.scrollTo = (position) => calls.scroll.push(position);
  browser.addEventListener('studio:navigate', () => {
    calls.navigation.push(browser.location.pathname + browser.location.search);
  });
  Object.defineProperty(globalThis, 'window', { configurable: true, value: browser });
  t.after(() => {
    if (previous) Object.defineProperty(globalThis, 'window', previous);
    else delete globalThis.window;
  });
  return calls;
}

test('opening a new page resets scroll after publishing the new route', (t) => {
  const calls = browserAt(t, '/login');
  navigateRoute('/studio');
  assert.deepEqual(calls.history, ['pushState']);
  assert.deepEqual(calls.navigation, ['/studio']);
  assert.deepEqual(calls.scroll, [{ top: 0, left: 0, behavior: 'instant' }]);
});

test('route replacement also starts the new page at the top', (t) => {
  const calls = browserAt(t, '/login');
  navigateRoute('/studio/settings/account?return=profile', { replace: true });
  assert.deepEqual(calls.history, ['replaceState']);
  assert.equal(calls.scroll.length, 1);
});

test('query-only navigation preserves the current reading position', (t) => {
  const calls = browserAt(t, '/studio/campaigns');
  navigateRoute('/studio/campaigns?run=campaign-1');
  assert.deepEqual(calls.navigation, ['/studio/campaigns?run=campaign-1']);
  assert.deepEqual(calls.scroll, []);
});

test('hash destinations retain their anchor instead of being forced to the page top', (t) => {
  const calls = browserAt(t, '/studio');
  navigateRoute('/home#clientes');
  assert.deepEqual(calls.scroll, []);
  assert.equal(window.location.hash, '#clientes');
});
