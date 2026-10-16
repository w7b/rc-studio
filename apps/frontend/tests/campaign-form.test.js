import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync, readdirSync } from 'node:fs';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { buildRunRequest } from '../src/features/campaigns/run-request.js';
import { component } from './render-component.js';

const sourceRoot = new URL('../src/', import.meta.url);

test('every JSX component imports React for the classic runtime', () => {
  for (const path of readdirSync(sourceRoot, { recursive: true }).filter((path) =>
    path.endsWith('.jsx')
  )) {
    const source = readFileSync(new URL(path.replaceAll('\\', '/'), sourceRoot), 'utf8');
    assert.match(
      source,
      /import\s+React(?:\s*,[\s\S]*?)?\s+from\s+['"]react['"]/,
      `${path} needs React in scope`
    );
  }
});

test('campaign form renders Required and empty confirmed facts at runtime', () => {
  const CampaignForm = component('features/campaigns/CampaignForm.jsx');
  const html = renderToStaticMarkup(
    React.createElement(CampaignForm, { products: [], initial: { mode: 'demo' } })
  );
  assert.match(html, /aria-label="obrigatório"/);
  assert.match(html, /Origem: Produto/);
  assert.match(html, /Origem: Referência visual/);
  assert.equal((html.match(/checked="" value="none"/g) || []).length, 2);
  assert.doesNotMatch(html, /type="file"/);
  const facts = html.match(/<textarea[^>]*rows="3"[^>]*>[\s\S]*?<\/textarea>/)?.[0];
  assert.ok(facts);
  assert.doesNotMatch(facts, /placeholder=/);
  assert.match(facts, /><\/textarea>/);
});

test('editing a campaign keeps saved products and uploaded references in their own source cards', () => {
  const CampaignForm = component('features/campaigns/CampaignForm.jsx');
  const html = renderToStaticMarkup(
    React.createElement(CampaignForm, {
      products: [{ id: 'product-1', title: 'Café da loja' }],
      initial: {
        mode: 'demo',
        product_id: 'product-1',
        reference: { name: 'composicao.png' },
        reference_id: 'previous-reference',
      },
    })
  );
  assert.match(html, /Café da loja/);
  assert.match(html, /composicao.png/);
  assert.equal((html.match(/type="file"/g) || []).length, 1);
  assert.doesNotMatch(html, /Referência salva/);
  assert.doesNotMatch(html, /Salvar no Brand Kit/);
});

test('an uploaded product stays active when an edited campaign also has a saved product id', () => {
  const CampaignForm = component('features/campaigns/CampaignForm.jsx');
  const html = renderToStaticMarkup(
    React.createElement(CampaignForm, {
      products: [{ id: 'product-1', title: 'Produto anterior' }],
      initial: {
        mode: 'demo',
        product_id: 'product-1',
        photo: { name: 'produto-atual.png' },
      },
    })
  );
  assert.match(html, /produto-atual.png/);
  assert.match(html, /Salvar no Brand Kit/);
  assert.doesNotMatch(html, /Produto anterior/);
});

test('both consultation choices render without a React runtime error', () => {
  const Consultations = component('features/consultations/Consultations.jsx');
  const html = renderToStaticMarkup(React.createElement(Consultations, { config: { models: [] } }));
  assert.match(html, /Performance Marketing Manager/);
  assert.match(html, /Marketing Analyst \+ SEO/);
  assert.match(html, /Configure um modelo de texto/);
});

test('consultations select an available external model when the default has no key', () => {
  const Consultations = component('features/consultations/Consultations.jsx');
  const html = renderToStaticMarkup(
    React.createElement(Consultations, {
      config: {
        configured: true,
        models: [
          { id: 'openai:default', available: false },
          { id: 'nvidia:available', available: true },
        ],
      },
    })
  );
  assert.match(html, /value="nvidia:available" selected=""/);
});

test('demo payload disables paid generation and uploads override library selections', () => {
  const payload = buildRunRequest({
    request: 'Teste',
    facts: ' Confirmado\n\n',
    selection: 'demo',
    image: true,
    product: 'old-product',
    referenceId: 'old-reference',
    upload: 'image',
    referenceUpload: 'reference',
    publication: { kind: 'feed', preset: 'feed_portrait', slides: 1 },
  });
  assert.equal(payload.generate_image, false);
  assert.equal(payload.model_id, null);
  assert.equal(payload.image_model_id, null);
  assert.equal(payload.product_id, null);
  assert.equal(payload.reference_id, null);
  assert.deepEqual(payload.confirmed_facts, ['Confirmado']);
});
