import assert from 'node:assert/strict';
import { test } from 'node:test';
import { componentModule, renderComponent as render } from './render-component.js';

test('field help is a named keyboard and touch control that cannot submit the form', () => {
  const html = render('shared/components/FieldHelp.jsx', { text: 'Use informações confirmadas.' });
  assert.match(html, /<button[^>]*type="button"[^>]*aria-label="Mais informações"/);
  assert.doesNotMatch(html, /role="img"/);
});

test('search select exposes both its field label and current selection in its accessible name', () => {
  const html = render('shared/components/SearchSelect.jsx', {
    label: 'Produto',
    value: 'cafe',
    options: [{ value: 'cafe', label: 'Café da loja', description: 'Pacote de 500 g' }],
    onChange() {},
  });
  const ids = html.match(/aria-labelledby="([^"]+)"/)?.[1].split(' ');
  assert.equal(ids?.length, 2);
  assert.ok(html.includes(`id="${ids[0]}"`));
  assert.ok(html.includes(`id="${ids[1]}"`));
  assert.match(html, /Café da loja/);
  assert.match(html, /Pacote de 500 g/);
});

test('breadcrumbs preserve ordered route hierarchy and identify the current page', () => {
  const html = render('app/StudioBreadcrumbs.jsx', { page: 'references', onNavigate() {} });
  assert.match(html, /<ol/);
  assert.equal((html.match(/<li /g) || []).length, 3);
  assert.match(html, /href="\/studio\/library"/);
  assert.match(html, /aria-current="page">Referências/);
});

test('rotating text writes complete segments before erasing and cycles back to the first', () => {
  const { advanceText } = componentModule('shared/components/RotatingText.jsx');
  const words = ['Padarias', 'Óticas e relojoarias'];
  let state = { index: 0, length: 0, phase: 'type' };
  const completed = [];
  for (let step = 0; step < 200 && completed.length < 3; step++) {
    const next = advanceText(state, words);
    if (next.phase === 'hold' && state.phase === 'type') {
      completed.push(words[next.index].slice(0, next.length));
    }
    state = next;
  }
  assert.deepEqual(completed, [words[0], words[1], words[0]]);
});

test('pausing a partially erased category keeps a complete readable word', () => {
  const { displayText } = componentModule('shared/components/RotatingText.jsx');
  const state = { index: 1, length: 3, phase: 'erase' };
  const words = ['Padarias', 'Óticas e relojoarias'];
  assert.equal(displayText(state, words, { paused: true }), 'Óticas e relojoarias');
  assert.equal(displayText(state, words), 'Óti');
  assert.equal(displayText(state, words, { reduced: true }), 'comércio local');
  assert.equal(displayText(state, []), 'comércio local');
});

test('rotating text starts readable, ignores empty categories, and has an empty-list fallback', () => {
  const previousWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');
  const previousDocument = Object.getOwnPropertyDescriptor(globalThis, 'document');
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: { matchMedia: () => ({ matches: false }) },
  });
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { hidden: false } });
  try {
    const html = render('shared/components/RotatingText.jsx', { words: ['', '  ', 'Padarias'] });
    assert.match(html, /aria-hidden="true">Padarias/);
    assert.match(render('shared/components/RotatingText.jsx', { words: [] }), /comércio local/);
  } finally {
    if (previousWindow) Object.defineProperty(globalThis, 'window', previousWindow);
    else delete globalThis.window;
    if (previousDocument) Object.defineProperty(globalThis, 'document', previousDocument);
    else delete globalThis.document;
  }
});
