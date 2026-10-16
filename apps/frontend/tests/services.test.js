import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { afterEach, test } from 'node:test';

const originalFetch = globalThis.fetch;
const originalFileReader = globalThis.FileReader;

async function service(name) {
  const url = new URL(`../src/services/${name}.js`, import.meta.url);
  assert.ok(existsSync(url), `The ${name} service must own this behavior`);
  return import(url.href);
}

function reply(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(async () => {
  globalThis.fetch = originalFetch;
  globalThis.FileReader = originalFileReader;
  if (existsSync(new URL('../src/services/http.js', import.meta.url))) {
    const { setCsrf, onSessionLost } = await service('http');
    setCsrf('');
    onSessionLost(null);
  }
});

test('JSON reads retain session credentials, avoid cache, and forward cancellation', async () => {
  const { requestJson } = await service('http');
  const controller = new AbortController();
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/config');
    assert.equal(options.credentials, 'same-origin');
    assert.equal(options.cache, 'no-store');
    assert.equal(options.signal, controller.signal);
    return reply({ shared: true });
  };
  assert.deepEqual(await requestJson('/api/config', { signal: controller.signal }), {
    shared: true,
  });
});

test('JSON writes use current CSRF and preserve an explicit standalone token', async () => {
  const { postJson, setCsrf } = await service('http');
  const sent = [];
  globalThis.fetch = async (url, options) => {
    sent.push({ url, ...options });
    return reply({ accepted: true });
  };
  setCsrf('session-token');
  assert.deepEqual(await postJson('/api/runs', { request: 'Café' }), { accepted: true });
  setCsrf('rotated-token');
  await postJson('/api/runs', {}, 'standalone-token');
  await postJson('/api/runs', {});
  assert.equal(sent[0].method, 'POST');
  assert.equal(sent[0].headers['Content-Type'], 'application/json');
  assert.equal(sent[0].headers['X-App-Token'], 'session-token');
  assert.equal(sent[0].body, '{"request":"Café"}');
  assert.equal(sent[1].headers['X-App-Token'], 'standalone-token');
  assert.equal(sent[2].headers['X-App-Token'], 'rotated-token');
});

test('session expiry invokes the handler before trying to parse the response', async () => {
  const { requestJson, onSessionLost } = await service('http');
  let expired = 0;
  onSessionLost(() => expired++);
  globalThis.fetch = async () => new Response('expired', { status: 401 });
  await assert.rejects(requestJson('/api/runs'), /Sessão expirada/);
  assert.equal(expired, 1);
});

test('server errors and failed login messages reach the caller unchanged', async () => {
  const { requestJson } = await service('http');
  globalThis.fetch = async () => reply({ error: 'Credenciais inválidas' }, 401);
  await assert.rejects(requestJson('/api/login'), /Credenciais inválidas/);
  globalThis.fetch = async () => reply({}, 503);
  await assert.rejects(requestJson('/api/config'), /Não foi possível conectar ao app/);
});

test('proxy and malformed error responses expose a safe message with the HTTP status', async () => {
  const { requestJson } = await service('http');
  for (const [status, body, contentType] of [
    [502, '<html><h1>Bad Gateway</h1><pre>internal proxy details</pre></html>', 'text/html'],
    [504, 'upstream connection timed out', 'text/plain'],
    [500, '{"error":', 'application/json'],
    [503, 'null', 'application/json'],
    [502, '', 'text/html'],
  ]) {
    globalThis.fetch = async () =>
      new Response(body, {
        status,
        headers: { 'Content-Type': contentType },
      });
    await assert.rejects(requestJson('/api/runs'), {
      name: 'Error',
      message: `Não foi possível conectar ao app (HTTP ${status})`,
    });
  }
});

test('aborting an error response body is not converted into an HTTP failure', async () => {
  const { requestJson } = await service('http');
  globalThis.fetch = async () =>
    new Response(
      new ReadableStream({
        start(controller) {
          controller.error(new DOMException('Reading cancelled', 'AbortError'));
        },
      }),
      { status: 502 }
    );
  await assert.rejects(requestJson('/api/runs'), { name: 'AbortError' });
});

test('aborted network requests remain AbortErrors for lifecycle cleanup', async () => {
  const { requestJson } = await service('http');
  const controller = new AbortController();
  controller.abort();
  globalThis.fetch = async (_url, { signal }) => {
    signal.throwIfAborted();
  };
  await assert.rejects(requestJson('/api/runs', { signal: controller.signal }), {
    name: 'AbortError',
  });
});

test('account password changes rotate CSRF before the next write', async () => {
  const { accountService } = await service('account');
  const sent = [];
  globalThis.fetch = async (url, options) => {
    sent.push({ url, ...options });
    return reply(url.endsWith('/password') ? { csrf: 'new-session-token' } : { saved: true });
  };
  await accountService.changePassword({ current: 'old-password', password: 'new-password' });
  await accountService.updateDetails({
    name: 'Loja',
    email: ' owner@example.com ',
    phone: ' 123 ',
  });
  assert.equal(sent[1].headers['X-App-Token'], 'new-session-token');
  assert.deepEqual(JSON.parse(sent[1].body), {
    name: 'Loja',
    email: 'owner@example.com',
    phone: '123',
  });
});

test('drafts restore uploaded PNG and JPEG files and retain the original fields', async () => {
  const { campaignService } = await service('campaigns');
  globalThis.fetch = async (url) => {
    assert.equal(url, '/api/runs/run%2Fone/draft');
    return reply({ request: 'Café', upload: 'iVA=', reference_upload: '/9g=' });
  };
  const draft = await campaignService.getDraft('run/one');
  assert.equal(draft.id, 'run/one');
  assert.equal(draft.request, 'Café');
  assert.equal(draft.photo.name, 'produto.png');
  assert.equal(draft.photo.type, 'image/png');
  assert.deepEqual([...new Uint8Array(await draft.photo.arrayBuffer())], [137, 80]);
  assert.equal(draft.reference.name, 'referencia.jpg');
  assert.equal(draft.reference.type, 'image/jpeg');
});

test('library references become the correct campaign file input and preserve download errors', async () => {
  const { referenceService } = await service('references');
  const item = {
    id: 'ref-1',
    url: '/images/one.png',
    title: 'Café',
    extension: 'png',
    kind: 'product',
  };
  globalThis.fetch = async () => new Response(new Blob(['image'], { type: 'image/png' }));
  const draft = await referenceService.getCampaignDraft(item);
  assert.equal(draft.id, 'reference-ref-1');
  assert.equal(draft.photo.name, 'Café.png');
  assert.equal(draft.photo.type, 'image/png');
  assert.equal(await draft.photo.text(), 'image');
  assert.equal(draft.reference, undefined);
  const visual = await referenceService.getCampaignDraft({ ...item, kind: 'feed' });
  assert.equal(visual.reference.name, 'Café.png');
  globalThis.fetch = async () => new Response('', { status: 404 });
  await assert.rejects(
    referenceService.getCampaignDraft(item),
    /Não foi possível carregar a referência/
  );
});

test('URL builders keep identifiers inside their path segments and query values', async () => {
  const { campaignService } = await service('campaigns');
  const { referenceService } = await service('references');
  const { adminService } = await service('admin');
  assert.equal(
    campaignService.fileUrl('run/one', 'role name.json'),
    '/api/runs/run%2Fone/files/role%20name.json'
  );
  assert.equal(referenceService.downloadUrl('ref/one'), '/api/references/ref%2Fone/download');
  globalThis.fetch = async (url) => {
    assert.equal(url, '/api/admin/tenants/model-keys?tenant_id=tenant%26other');
    return reply({ providers: [] });
  };
  assert.deepEqual(await adminService.getModelKeys('tenant&other'), { providers: [] });
});

test('admin writes normalize optional tenant paths and encode media deletion identifiers', async () => {
  const { adminService } = await service('admin');
  const { mediaService } = await service('media');
  const sent = [];
  globalThis.fetch = async (url, options) => {
    sent.push({ url, ...options });
    return reply({ saved: true });
  };
  await adminService.createTenant({ name: 'Loja', root_path: '   ' });
  await mediaService.remove('folder/photo', 'references', 'explicit-token');
  assert.deepEqual(JSON.parse(sent[0].body), { name: 'Loja', root_path: null });
  assert.equal(sent[1].url, '/api/references/folder%2Fphoto/delete');
  assert.equal(sent[1].headers['X-App-Token'], 'explicit-token');
});

test('file uploads strip the data URL prefix and propagate read failures', async () => {
  const { fileData } = await service('files');
  globalThis.FileReader = class {
    readAsDataURL(file) {
      if (file.fail) return this.onerror();
      this.result = 'data:image/png;base64,aW1hZ2U=';
      this.onload();
    }
  };
  assert.equal(await fileData({}), 'aW1hZ2U=');
  await assert.rejects(fileData({ fail: true }), /Não foi possível ler a imagem/);
});
