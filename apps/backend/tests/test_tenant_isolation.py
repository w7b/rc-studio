"""Proof that one store cannot reach another's data.

The load-bearing fact here is uncomfortable: media ids are sha256 of a path relative to
the data root, and reference ids are sha256 of the file's own bytes. Two stores therefore
produce *identical* ids for identical content. "The id is unguessable" is not a defence.
The only thing that separates stores is that every id is resolved against the session's
root, and never by searching. These tests exist to keep that true.
"""
import base64
import json
import shutil
import threading
from http.cookies import SimpleCookie
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from identity_fake import FakeIdentityStore
from realcenter_marketing.application.identity.service import IdentityService
from realcenter_marketing.bootstrap.platform import Identity
from realcenter_marketing.infrastructure.identity.rate_limit import MemoryRateLimiter
from realcenter_marketing.infrastructure.persistence.filesystem import media_catalog
from realcenter_marketing.presentation.http.server import make_server


class FastHasher:
    def hash(self, password):
        return 'fake$' + password

    def verify(self, password, encoded):
        return encoded == 'fake$' + password

    def dummy_verify(self):
        pass


class NoDatabase:
    def close(self):
        pass


@pytest.fixture
def png_bytes():
    import io
    from PIL import Image
    out = io.BytesIO()
    Image.new('RGB', (1152, 1440), 'orange').save(out, format='PNG')
    return out.getvalue()


@pytest.fixture
def two_stores(root, isolated_root, tmp_path):
    """Two complete data roots, plus a signed-in account for each.

    They are built from the `root` fixture rather than from `isolated_root`, which is
    tmp_path itself — copying that into a child of itself recurses forever.
    """
    roots = {}
    for slug in ('loja-a', 'loja-b'):
        target = tmp_path / 'stores' / slug
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(root, target)
        roots[slug] = target

    store = FakeIdentityStore()
    service = IdentityService(store, FastHasher(), MemoryRateLimiter())
    for slug in roots:
        tenant = store.create_tenant(slug, slug.upper(), str(roots[slug]))
        user = store.create_user(f'{slug}@loja.com.br', 'fake$senha-bem-comprida')
        store.grant(user.id, tenant.id, 'OWNER')

    identity = Identity(service=service, database=NoDatabase(), providers={})
    server = make_server(isolated_root, 0, identity=identity)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        yield base, roots, {slug: sign_in(base, f'{slug}@loja.com.br') for slug in roots}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)


def sign_in(base, email):
    body = json.dumps({'email': email, 'password': 'senha-bem-comprida'}).encode()
    response = urlopen(Request(base + '/api/login', data=body, headers={
        'Content-Type': 'application/json', 'Origin': base}))
    jar = SimpleCookie()
    jar.load(response.headers['Set-Cookie'])
    return {'Cookie': f'rcs_session={jar["rcs_session"].value}',
            'X-App-Token': json.load(response)['csrf']}


def get(base, path, auth):
    return urlopen(Request(base + path, headers={'Cookie': auth['Cookie']}))


def write_media(root, relative, content):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


def test_identical_paths_collide_but_are_never_cross_served(two_stores):
    """The central test. If someone 'fixes' the collision by changing the hash scheme,
    this fails and forces a conversation about the ADR 001 identity requirement."""
    base, roots, auth = two_stores
    relative = 'brand/products/reference-only/logo.png'
    write_media(roots['loja-a'], relative, b'\x89PNG-conteudo-da-loja-a')
    write_media(roots['loja-b'], relative, b'\x89PNG-conteudo-da-loja-b')

    ids_a, ids_b = media_catalog(roots['loja-a']), media_catalog(roots['loja-b'])
    shared_ids = set(ids_a) & set(ids_b)
    # Documented as a fact, not assumed away: the ids are the same.
    assert shared_ids, 'caminhos relativos iguais devem produzir o mesmo id'

    media_id = shared_ids.pop()
    assert get(base, f'/media/{media_id}', auth['loja-a']).read() == b'\x89PNG-conteudo-da-loja-a'
    assert get(base, f'/media/{media_id}', auth['loja-b']).read() == b'\x89PNG-conteudo-da-loja-b'


def test_a_run_of_one_store_is_invisible_to_the_other(two_stores):
    base, roots, auth = two_stores
    data = json.dumps({'request': 'Campanha da loja A', 'mode': 'demo'}).encode()
    run_id = json.load(urlopen(Request(base + '/api/runs', data=data, headers={
        'Content-Type': 'application/json', 'Origin': base, **auth['loja-a']})))['id']

    listing = json.load(get(base, '/api/runs', auth['loja-b']))
    assert run_id not in json.dumps(listing)
    assert listing['runs'] == []

    # 404 rather than 403: confirming existence is itself a disclosure.
    for path in (f'/api/runs/{run_id}/draft', f'/api/runs/{run_id}/files/legenda-feed.txt'):
        with pytest.raises(HTTPError) as error:
            get(base, path, auth['loja-b'])
        assert error.value.code == 404, path

    assert (roots['loja-a'] / 'campaigns/runs' / run_id).is_dir()


def test_one_store_cannot_delete_another_store_run(two_stores):
    base, roots, auth = two_stores
    data = json.dumps({'request': 'Campanha da loja A', 'mode': 'demo'}).encode()
    run_id = json.load(urlopen(Request(base + '/api/runs', data=data, headers={
        'Content-Type': 'application/json', 'Origin': base, **auth['loja-a']})))['id']

    with pytest.raises(HTTPError) as error:
        urlopen(Request(base + f'/api/runs/{run_id}/delete', data=b'{}', headers={
            'Content-Type': 'application/json', 'Origin': base, **auth['loja-b']}))
    assert error.value.code in (400, 404)
    assert (roots['loja-a'] / 'campaigns/runs' / run_id).is_dir()


def test_usage_and_activity_are_scoped_to_the_session(two_stores):
    base, _, auth = two_stores
    data = json.dumps({'request': 'Campanha da loja A', 'mode': 'demo'}).encode()
    urlopen(Request(base + '/api/runs', data=data, headers={
        'Content-Type': 'application/json', 'Origin': base, **auth['loja-a']}))

    for path in ('/api/usage', '/api/system/activity', '/api/media'):
        payload = json.dumps(json.load(get(base, path, auth['loja-b'])))
        assert 'loja-a' not in payload, path


def test_a_reference_shared_by_content_hash_stays_in_its_own_store(two_stores, png_bytes):
    base, _, auth = two_stores
    body = json.dumps({'title': 'Mesma imagem', 'kind': 'story',
                       'upload': base64.b64encode(png_bytes).decode()}).encode()
    created = {}
    for slug in ('loja-a', 'loja-b'):
        response = urlopen(Request(base + '/api/references', data=body, headers={
            'Content-Type': 'application/json', 'Origin': base, **auth[slug]}))
        created[slug] = json.load(response)['id']
    # Identical bytes hash to the same id in both stores.
    assert created['loja-a'] == created['loja-b']

    for slug in ('loja-a', 'loja-b'):
        listing = json.load(get(base, '/api/references', auth[slug]))
        assert len(listing) == 1
        assert get(base, f'/api/references/{created[slug]}/image', auth[slug]).status == 200


def test_every_data_route_refuses_an_anonymous_caller(two_stores):
    """A literal list, so the guarantee survives the twentieth route someone adds."""
    base, _, _ = two_stores
    for path in ('/api/runs', '/api/media', '/api/references', '/api/usage', '/api/formats',
                 '/api/system', '/api/system/activity', '/media/qualquer',
                 '/api/runs/run-' + 'a' * 32 + '/draft'):
        with pytest.raises(HTTPError) as error:
            urlopen(base + path)
        assert error.value.code == 401, path


@pytest.mark.parametrize('endpoint', ['references', 'media'])
def test_library_delete_checks_session_csrf_and_only_removes_current_store(two_stores, png_bytes, endpoint):
    base, roots, auth = two_stores
    body = json.dumps({'title': 'Mesmo produto', 'kind': 'product', 'upload': base64.b64encode(png_bytes).decode()}).encode()
    keys = {}
    for slug in roots:
        reference = json.load(urlopen(Request(base + '/api/references', data=body, headers={
            'Content-Type': 'application/json', 'Origin': base, **auth[slug]})))
        keys[slug] = reference['id'] if endpoint == 'references' else next(iter(media_catalog(roots[slug])))
    assert keys['loja-a'] == keys['loja-b']
    path = f'/api/{endpoint}/{keys["loja-a"]}/delete'
    for credentials, status in (({}, 401), ({'Cookie': auth['loja-a']['Cookie']}, 403)):
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + path, data=b'{}', headers={'Content-Type': 'application/json', 'Origin': base, **credentials}))
        assert error.value.code == status
    response = json.load(urlopen(Request(base + path, data=b'{}', headers={
        'Content-Type': 'application/json', 'Origin': base, **auth['loja-a']})))
    assert response['deleted'] == keys['loja-a']
    assert json.load(get(base, '/api/references', auth['loja-a'])) == []
    assert len(json.load(get(base, '/api/references', auth['loja-b']))) == 1
    assert len(media_catalog(roots['loja-b'])) == 1
    with pytest.raises(HTTPError) as error:
        urlopen(Request(base + path, data=b'{}', headers={
            'Content-Type': 'application/json', 'Origin': base, **auth['loja-a']}))
    assert error.value.code == 400
    assert len(media_catalog(roots['loja-b'])) == 1
