"""HTTP behaviour once the deployment is shared: nothing is readable without a session.

These run against the in-memory identity store, so the suite stays offline. The Postgres
adapter is covered by test_identity_postgres.py, which skips without a server.
"""
import json
import threading
from http.cookies import SimpleCookie
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.request import HTTPRedirectHandler, build_opener

import pytest

from identity_fake import FakeIdentityStore
from realcenter_marketing.application.identity.service import IdentityService
from realcenter_marketing.bootstrap.platform import Identity
from realcenter_marketing.infrastructure.identity.rate_limit import MemoryRateLimiter
from realcenter_marketing.presentation.http.server import make_server, spa_route


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
def shared(isolated_root):
    store = FakeIdentityStore()
    service = IdentityService(store, FastHasher(), MemoryRateLimiter())
    loja = store.create_tenant('mercado-central', 'Mercado Central')
    user = store.create_user('dono@loja.com.br', 'fake$senha-bem-comprida', 'Dono')
    store.grant(user.id, loja.id, 'OWNER')
    identity = Identity(service=service, database=NoDatabase(), providers={})

    server = make_server(isolated_root, 0, identity=identity)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f'http://127.0.0.1:{server.server_port}', store
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def sign_in(base, email='dono@loja.com.br', password='senha-bem-comprida'):
    body = json.dumps({'email': email, 'password': password}).encode()
    request = Request(base + '/api/login', data=body, headers={
        'Content-Type': 'application/json', 'Origin': base})
    response = urlopen(request)
    jar = SimpleCookie()
    jar.load(response.headers['Set-Cookie'])
    payload = json.load(response)
    return f'rcs_session={jar["rcs_session"].value}', payload['csrf'], response


def test_reading_campaign_data_requires_a_session(shared):
    _, base, _ = shared
    for path in ('/api/runs', '/api/media', '/api/references', '/api/usage', '/api/formats'):
        with pytest.raises(HTTPError) as error:
            urlopen(base + path)
        assert error.value.code == 401, path


def test_old_open_invite_accepts_the_email_sent_by_the_form(shared):
    server, base, store = shared
    tenant = store.tenant_by_slug('mercado-central')
    raw = server.identity.service.create_invite(tenant.id, 'DEFAULT')
    body = json.dumps({'token': raw, 'email': 'convidado@exemplo.com',
                       'password': 'senha-nova-comprida', 'name': 'Convidado'}).encode()
    response = urlopen(Request(base + '/api/invites/accept', data=body,
                               headers={'Content-Type': 'application/json', 'Origin': base}))
    assert response.status == 200
    assert 'HttpOnly' in response.headers['Set-Cookie']
    assert json.load(response)['tenant']['slug'] == tenant.slug
    assert store.user_by_email('convidado@exemplo.com').name == 'Convidado'
    with pytest.raises(HTTPError) as reused:
        urlopen(Request(base + '/api/invites/accept', data=body,
                        headers={'Content-Type': 'application/json', 'Origin': base}))
    assert reused.value.code == 400


def test_config_no_longer_hands_out_a_token_before_login(shared):
    _, base, _ = shared
    config = json.load(urlopen(base + '/api/config'))
    # The CSRF token now belongs to a session; serving it here would serve it to anyone.
    assert 'token' not in config
    assert config['shared'] is True
    assert json.load(urlopen(base + '/api/session'))['authenticated'] is False


def test_sign_in_sets_a_hardened_cookie_and_opens_the_session(shared):
    _, base, _ = shared
    cookie, csrf, response = sign_in(base)
    header = response.headers['Set-Cookie']
    assert 'HttpOnly' in header and 'SameSite=Lax' in header and 'Path=/' in header
    # Secure is off only because the suite speaks plain HTTP to loopback.
    assert 'Secure' not in header

    session = json.load(urlopen(Request(base + '/api/session', headers={'Cookie': cookie})))
    assert session['authenticated'] is True
    assert session['tenant']['slug'] == 'mercado-central'
    assert session['role'] == 'OWNER'
    assert session['csrf'] == csrf
    assert json.load(urlopen(Request(base + '/api/runs', headers={'Cookie': cookie})))['runs'] == []


def test_wrong_password_is_401_and_reveals_nothing(shared):
    _, base, _ = shared
    for email in ('dono@loja.com.br', 'ninguem@loja.com.br'):
        body = json.dumps({'email': email, 'password': 'errada'}).encode()
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + '/api/login', data=body, headers={
                'Content-Type': 'application/json', 'Origin': base}))
        assert error.value.code == 401
        assert json.load(error.value)['error'] == 'E-mail ou senha inválidos'


def test_a_write_needs_the_csrf_token_of_its_own_session(shared):
    _, base, _ = shared
    cookie, csrf, _ = sign_in(base)
    other_cookie, other_csrf, _ = sign_in(base)
    data = json.dumps({'request': 'Campanha de teste', 'mode': 'demo'}).encode()

    def post(headers):
        return urlopen(Request(base + '/api/runs', data=data, headers={
            'Content-Type': 'application/json', 'Origin': base, **headers}))

    for headers in ({'Cookie': cookie}, {'Cookie': cookie, 'X-App-Token': other_csrf}):
        with pytest.raises(HTTPError) as error:
            post(headers)
        assert error.value.code == 403
    assert json.load(post({'Cookie': cookie, 'X-App-Token': csrf}))['id']


def test_a_write_without_a_session_is_401(shared):
    _, base, _ = shared
    data = json.dumps({'request': 'Campanha de teste', 'mode': 'demo'}).encode()
    with pytest.raises(HTTPError) as error:
        urlopen(Request(base + '/api/runs', data=data, headers={
            'Content-Type': 'application/json', 'Origin': base}))
    assert error.value.code == 401


def test_logout_invalidates_the_cookie(shared):
    _, base, _ = shared
    cookie, csrf, _ = sign_in(base)
    urlopen(Request(base + '/api/logout', data=b'{}', headers={
        'Content-Type': 'application/json', 'Origin': base, 'Cookie': cookie, 'X-App-Token': csrf}))
    assert json.load(urlopen(Request(base + '/api/session', headers={'Cookie': cookie})))['authenticated'] is False
    with pytest.raises(HTTPError) as error:
        urlopen(Request(base + '/api/runs', headers={'Cookie': cookie}))
    assert error.value.code == 401


def test_logs_are_restricted_to_the_owner(shared):
    _, base, store = shared
    cookie, _, _ = sign_in(base)
    assert urlopen(Request(base + '/api/logs', headers={'Cookie': cookie})).status == 200

    loja = store.tenant_by_slug('mercado-central')
    editor = store.create_user('editor@loja.com.br', 'fake$senha-bem-comprida')
    store.grant(editor.id, loja.id, 'DEFAULT')
    editor_cookie, _, _ = sign_in(base, 'editor@loja.com.br')
    with pytest.raises(HTTPError) as error:
        urlopen(Request(base + '/api/logs', headers={'Cookie': editor_cookie}))
    assert error.value.code == 403


def test_oauth_start_is_404_when_google_is_not_configured(shared):
    _, base, _ = shared
    with pytest.raises(HTTPError) as error:
        urlopen(base + '/api/auth/google')
    assert error.value.code == 404


def test_oauth_state_pkce_callback_and_studio_redirect(shared):
    from urllib.parse import parse_qs, urlsplit
    from realcenter_marketing.infrastructure.identity.oauth import GoogleOAuthProvider
    from realcenter_marketing.application.identity.model import OAuthProfile
    from realcenter_marketing.presentation.http import cookies
    server, base, _ = shared

    class Provider(GoogleOAuthProvider):
        def exchange(self, code, verifier, redirect_uri):
            assert code == 'test-code' and len(verifier) >= 43
            assert redirect_uri == base + '/api/auth/google/callback'
            return OAuthProfile('google', 'verified-subject', 'dono@loja.com.br', True)

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    server.identity.providers['google'] = Provider('fake-client-id', 'fake-client-secret')
    opener = build_opener(NoRedirect())
    with pytest.raises(HTTPError) as start:
        opener.open(base + '/api/auth/google')
    assert start.value.code == 303
    query = parse_qs(urlsplit(start.value.headers['Location']).query)
    assert query['code_challenge_method'] == ['S256']
    assert 'fake-client-secret' not in start.value.headers['Location']
    jar = SimpleCookie()
    jar.load(start.value.headers['Set-Cookie'])
    header = {'Cookie': f'{cookies.OAUTH_COOKIE}={jar[cookies.OAUTH_COOKIE].value}'}
    with pytest.raises(HTTPError) as wrong:
        opener.open(Request(base + '/api/auth/google/callback?code=test-code&state=wrong', headers=header))
    assert wrong.value.headers['Location'] == '/login?erro=oauth'
    with pytest.raises(HTTPError) as success:
        opener.open(Request(base + '/api/auth/google/callback?code=test-code&state=' + query['state'][0], headers=header))
    assert success.value.headers['Location'] == '/studio'
    assert any('rcs_session=' in value for value in success.value.headers.get_all('Set-Cookie'))


def test_client_routes_serve_the_shell_but_dotfiles_still_404(shared):
    _, base, _ = shared
    for path in ('/login', '/convite', '/sobre', '/app/campanha'):
        assert spa_route(path), path
    # The guarantees that existed before the fallback must survive it.
    for path in ('/.env', '/assets/../../.env', '/api/runs', '/media/abc'):
        assert not spa_route(path), path
    for path in ('/.env', '/assets/../../.env'):
        with pytest.raises(HTTPError) as error:
            urlopen(base + path)
        assert error.value.code == 404


@pytest.mark.parametrize('trusted', [False, True])
def test_login_rate_limit_uses_forwarded_ip_only_from_a_trusted_proxy(shared, trusted):
    server, base, _ = shared
    server.trusted_proxies = ('127.0.0.1',) if trusted else ()
    # Distinct real clients do not consume one shared proxy budget. A direct
    # client spoofing the same headers still exhausts its single socket budget.
    for index in range(21):
        body = json.dumps({'email': f'unknown{index}@example.test', 'password': 'wrong'}).encode()
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + '/api/login', data=body, headers={
                'Content-Type': 'application/json', 'Origin': base,
                'X-Real-IP': f'203.0.113.{index + 1}'}))
        assert error.value.code == (429 if index == 20 and not trusted else 401)
