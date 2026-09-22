import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  breadcrumbsFor,
  campaignUrl,
  pageFor,
  routeRedirect,
  STUDIO_MENU,
  STUDIO_ROUTES,
  PAGE_MODULE,
} from '../src/shared/navigation/routes.js';

test('every menu item resolves to a route and each child follows an existing parent', () => {
  const ids = STUDIO_MENU.map(({ id }) => id);
  assert.ok(ids.length > 0);
  for (const { id, under } of STUDIO_MENU) {
    assert.equal(pageFor(STUDIO_ROUTES[id]), id);
    if (under) {
      assert.ok(ids.includes(under), `${id} has no parent ${under}`);
      assert.ok(ids.indexOf(under) < ids.indexOf(id), `${id} precedes its parent`);
    }
  }
});

test('anonymous visitors leave every private and invalid route', () => {
  for (const route of [...Object.values(STUDIO_ROUTES), '/missing']) {
    assert.equal(routeRedirect(route, 'anonymous'), '/');
  }
  for (const route of ['/', '/home', '/login?erro=oauth', '/convite']) {
    assert.equal(routeRedirect(route, 'anonymous'), null);
  }
});

test('only OWNER reaches administration and owner modules', () => {
  for (const role of ['DEFAULT', 'PAID', undefined]) {
    for (const path of ['/admin', '/studio/agentes', '/studio/logs']) {
      assert.equal(routeRedirect(path, 'ready', role), '/home');
    }
  }
  assert.equal(routeRedirect('/admin', 'ready', 'OWNER'), null);
});

test('disabled modules deny both the parent and nested page while settings remain available', () => {
  for (const [module, pages] of [
    ['meta_ads', ['ads', 'consultations']],
    ['art_lib', ['gallery', 'references']],
    ['campaigns', ['create', 'history']],
  ]) {
    for (const page of pages) {
      assert.equal(PAGE_MODULE[page], module);
      assert.equal(
        routeRedirect(STUDIO_ROUTES[page], 'ready', 'PAID', { [module]: false }),
        '/studio/settings/account'
      );
    }
  }
  for (const page of ['config', 'account', 'security', 'store', 'brandkit']) {
    assert.equal(routeRedirect(STUDIO_ROUTES[page], 'ready', 'PAID', {}), null);
    assert.equal(STUDIO_MENU.find(({ id }) => id === page).sessionOnly, true);
  }
});

test('legacy links redirect to canonical URLs without losing their query', () => {
  const aliases = {
    '/studio/campaings': '/studio/campaigns',
    '/studio/art-lib': '/studio/library',
    '/studio/references': '/studio/library/references',
    '/studio/consultoria': '/studio/meta-ads/consultations',
    '/studio/config': '/studio/settings/brand-kit',
    '/studio/account': '/studio/settings/account',
  };
  for (const [previous, current] of Object.entries(aliases)) {
    assert.equal(
      routeRedirect(`${previous}?run=abc&type=product`, 'ready', 'OWNER'),
      `${current}?run=abc&type=product`
    );
    assert.equal(routeRedirect(current, 'ready', 'OWNER'), null);
    assert.equal(routeRedirect(previous, 'anonymous'), '/');
  }
  const target = routeRedirect('/studio/references?type=product', 'ready', 'PAID', {
    art_lib: false,
  });
  assert.equal(
    routeRedirect(target, 'ready', 'PAID', { art_lib: false }),
    '/studio/settings/account'
  );
});

test('deep-linked campaigns and route normalization survive reload', () => {
  assert.equal(campaignUrl('run-abc'), '/studio/campaigns?run=run-abc');
  assert.equal(pageFor(campaignUrl('run-abc')), 'result');
  assert.equal(pageFor('/studio/campaigns'), 'history');
  assert.equal(routeRedirect('/invalid', 'ready', 'OWNER'), '/home');
  assert.equal(routeRedirect('/studio/?x=1', 'ready', 'OWNER'), '/studio?x=1');
  assert.equal(routeRedirect('/login', 'ready', 'OWNER'), '/studio');
});

test('breadcrumbs expose the same parent destinations as the sidebar', () => {
  for (const { id, under } of STUDIO_MENU.filter(({ under }) => under)) {
    const crumbs = breadcrumbsFor(id);
    assert.deepEqual(
      crumbs.map(({ id }) => id),
      [under, id]
    );
    assert.equal(crumbs[0].label, STUDIO_MENU.find(({ id }) => id === under).label);
    assert.ok(STUDIO_ROUTES[crumbs[0].id]);
  }
  assert.deepEqual(
    breadcrumbsFor('result').map(({ id }) => id),
    ['history', 'result']
  );
  assert.deepEqual(breadcrumbsFor('missing'), []);
});
