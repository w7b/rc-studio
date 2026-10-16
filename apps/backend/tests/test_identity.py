"""Identidade, sessão, login HTTP e cotas."""
from datetime import timedelta
import pytest
from identity_fake import FakeIdentityStore, FastHasher
from studio_ai.application.identity.errors import AccountError, AuthError, InviteError, NoAccess, RateLimited
from studio_ai.application.identity.model import ABSOLUTE_LIFETIME, IDLE_LIFETIME, OAuthProfile, now
from studio_ai.application.identity.service import IdentityService, token_hash
from studio_ai.infrastructure.identity.passwords import ScryptHasher
from studio_ai.infrastructure.identity.rate_limit import MemoryRateLimiter
import json
import threading
from http.cookies import SimpleCookie
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.request import HTTPRedirectHandler, build_opener
from studio_ai.application.identity.service import IdentityService
from studio_ai.bootstrap.platform import Identity
from studio_ai.presentation.http.server import make_server, spa_route
from studio_ai.application.identity.quota import PLANS, QuotaError, UsageQuota, limits_for
from studio_ai.infrastructure.identity.memory_quotas import MemoryQuotaLedger
from studio_ai.presentation.http.server import make_server


# ---- identity ----------------------------------------------------------------

@pytest.fixture
def identity():
    store, hasher = FakeIdentityStore(), FastHasher()
    service = IdentityService(store, hasher, MemoryRateLimiter())
    loja = store.create_tenant('mercado-central', 'Mercado Central')
    user = store.create_user('dono@loja.com.br', hasher.hash('senha-bem-comprida'), 'Dono')
    store.grant(user.id, loja.id, 'OWNER')
    return service, store, hasher, loja, user


def test_sign_in_returns_a_principal_scoped_to_one_store(identity):
    service, _, _, loja, user = identity
    raw, principal = service.sign_in('dono@loja.com.br', 'senha-bem-comprida')
    assert principal.user.id == user.id
    assert principal.tenant.id == loja.id
    assert principal.is_owner
    # The cookie value is never what gets stored.
    assert service.resolve(raw).tenant.slug == 'mercado-central'


def test_invite_accepts_eight_characters_but_rejects_seven(identity):
    service, _, _, loja, _ = identity
    raw = service.create_invite(loja.id, 'DEFAULT', 'nova@loja.com.br')
    with pytest.raises(InviteError, match='8 caracteres'):
        service.accept_invite(raw, password='Abc123!')
    session, principal = service.accept_invite(raw, password='Abc123!x')
    assert service.resolve(session).user.id == principal.user.id
    assert service.sign_in('nova@loja.com.br', 'Abc123!x')[1].user.id == principal.user.id


def test_password_change_accepts_eight_characters_but_rejects_seven(identity):
    service, _, _, _, user = identity
    session, principal = service.sign_in(user.email, 'senha-bem-comprida')
    with pytest.raises(AccountError, match='8 caracteres'):
        service.change_password(principal, 'senha-bem-comprida', 'Abc123!')
    assert service.resolve(session) is not None
    service.change_password(principal, 'senha-bem-comprida', 'Abc123!x')
    assert service.sign_in(user.email, 'Abc123!x')[1].user.id == user.id


def test_wrong_password_and_unknown_email_are_indistinguishable(identity):
    service, _, hasher, _, _ = identity
    with pytest.raises(AuthError) as wrong:
        service.sign_in('dono@loja.com.br', 'errada')
    with pytest.raises(AuthError) as unknown:
        service.sign_in('ninguem@loja.com.br', 'errada')
    assert str(wrong.value) == str(unknown.value)
    # The unknown address still paid for a hash, so timing does not disclose accounts.
    assert hasher.dummies == 1


def test_repeated_failures_are_rate_limited(identity):
    service, _, _, _, _ = identity
    for _ in range(5):
        with pytest.raises(AuthError):
            service.sign_in('dono@loja.com.br', 'errada')
    with pytest.raises(RateLimited):
        service.sign_in('dono@loja.com.br', 'senha-bem-comprida')


def test_a_session_dies_of_old_age_and_of_silence(identity):
    service, store, _, _, _ = identity
    raw, _ = service.sign_in('dono@loja.com.br', 'senha-bem-comprida')
    store.age_session(token_hash(raw), created_at=now() - ABSOLUTE_LIFETIME - timedelta(minutes=1))
    assert service.resolve(raw) is None
    assert store.session(token_hash(raw)) is None

    raw, _ = service.sign_in('dono@loja.com.br', 'senha-bem-comprida')
    store.age_session(token_hash(raw), last_seen_at=now() - IDLE_LIFETIME - timedelta(minutes=1))
    assert service.resolve(raw) is None


def test_sign_out_and_revoked_membership_both_end_the_session(identity):
    service, store, _, loja, user = identity
    raw, _ = service.sign_in('dono@loja.com.br', 'senha-bem-comprida')
    service.sign_out(raw)
    assert service.resolve(raw) is None

    raw, _ = service.sign_in('dono@loja.com.br', 'senha-bem-comprida')
    store.revoke(user.id, loja.id)
    # A cookie must not outlive the access it was granted for.
    assert service.resolve(raw) is None


def test_a_suspended_store_locks_out_its_open_sessions(identity):
    service, store, _, loja, _ = identity
    raw, _ = service.sign_in('dono@loja.com.br', 'senha-bem-comprida')
    store.suspend(loja.id)
    assert service.resolve(raw) is None


def test_csrf_is_bound_to_the_session(identity):
    service, _, _, _, _ = identity
    _, first = service.sign_in('dono@loja.com.br', 'senha-bem-comprida')
    _, second = service.sign_in('dono@loja.com.br', 'senha-bem-comprida')
    assert first.csrf != second.csrf
    assert service.check_csrf(first, first.csrf)
    # A token from another session must not authorize this one.
    assert not service.check_csrf(first, second.csrf)
    assert not service.check_csrf(first, '')


def profile(email='dono@loja.com.br', verified=True, subject='google-123'):
    return OAuthProfile(provider='google', subject=subject, email=email,
                        email_verified=verified, name='Dono')


def test_oauth_requires_a_verified_email(identity):
    service, _, _, _, _ = identity
    with pytest.raises(AuthError):
        service.sign_in_with_profile(profile(verified=False))


def test_oauth_links_to_the_existing_account_and_then_uses_the_subject(identity):
    service, store, _, _, user = identity
    _, principal = service.sign_in_with_profile(profile())
    assert principal.user.id == user.id
    assert store.identities[('google', 'google-123')] == user.id

    # The address may change at the provider; the subject is what identifies the person.
    _, again = service.sign_in_with_profile(profile(email='outro-endereco@gmail.com'))
    assert again.user.id == user.id
    assert len(store.users_by_id) == 1


def test_oauth_never_provisions_a_store_for_an_unknown_account(identity):
    service, store, _, _, _ = identity
    with pytest.raises(NoAccess):
        service.sign_in_with_profile(profile(email='estranho@gmail.com', subject='google-999'))
    # Authenticating proves who someone is, never that they bought anything.
    assert len(store.users_by_id) == 1
    assert len(store.tenants_by_id) == 1


def test_a_member_of_no_store_is_refused_even_with_the_right_password(identity):
    service, store, hasher, _, _ = identity
    store.create_user('sem-loja@loja.com.br', hasher.hash('senha-bem-comprida'))
    with pytest.raises(NoAccess):
        service.sign_in('sem-loja@loja.com.br', 'senha-bem-comprida')


def test_invite_creates_the_account_and_grants_exactly_one_store(identity):
    service, store, _, loja, _ = identity
    raw = service.create_invite(loja.id, 'DEFAULT', 'novo@loja.com.br')
    _, principal = service.accept_invite(raw, password='outra-senha-longa')
    assert principal.role == 'DEFAULT'
    assert principal.tenant.id == loja.id
    assert store.membership(principal.user.id, loja.id) == 'DEFAULT'


def test_an_invite_is_single_use_and_expires(identity):
    service, store, _, loja, _ = identity
    raw = service.create_invite(loja.id, 'DEFAULT', 'novo@loja.com.br')
    service.accept_invite(raw, password='outra-senha-longa')
    with pytest.raises(InviteError):
        service.accept_invite(raw, password='outra-senha-longa')

    stale = service.create_invite(loja.id, 'DEFAULT', 'atrasado@loja.com.br')
    current = store.invites[token_hash(stale)]
    store.invites[token_hash(stale)] = type(current)(current.tenant_id, current.role,
                                                     current.email, now() - timedelta(seconds=1))
    with pytest.raises(InviteError):
        service.accept_invite(stale, password='outra-senha-longa')


def test_invite_accepted_with_google_requires_a_verified_email(identity):
    service, _, _, loja, _ = identity
    raw = service.create_invite(loja.id, 'PAID', 'novo@loja.com.br')
    with pytest.raises(InviteError):
        service.accept_invite(raw, profile=profile(email='novo@loja.com.br', verified=False,
                                                   subject='google-777'))
    _, principal = service.accept_invite(raw, profile=profile(email='novo@loja.com.br',
                                                              subject='google-777'))
    assert principal.role == 'PAID'


def test_an_unknown_role_is_rejected_before_a_token_is_minted(identity):
    service, store, _, loja, _ = identity
    with pytest.raises(InviteError):
        service.create_invite(loja.id, 'SUPERUSUARIO', 'novo@loja.com.br')
    assert store.invites == {}


def test_open_invite_accepts_a_supplied_email_and_preserves_single_use(identity):
    service, store, _, loja, _ = identity
    raw = service.create_invite(loja.id, 'PAID')
    _, principal = service.accept_invite(raw, email='  NOVA@EXEMPLO.COM  ',
                                         password='senha-nova-comprida', name='Nova pessoa')
    assert principal.user.email == 'nova@exemplo.com'
    assert principal.user.name == 'Nova pessoa'
    assert principal.tenant.id == loja.id
    assert principal.role == 'PAID'
    assert not store.invite(token_hash(raw)).usable()


@pytest.mark.parametrize('email,password', [('', 'senha-nova-comprida'), ('invalido', 'senha-nova-comprida'),
                                           ('nova@exemplo.com', None), ('nova@exemplo.com', 'curta')])
def test_invalid_invite_fields_do_not_create_a_user_or_consume_the_invite(identity, email, password):
    service, store, _, loja, _ = identity
    raw = service.create_invite(loja.id, 'DEFAULT')
    with pytest.raises(InviteError):
        service.accept_invite(raw, email=email, password=password)
    assert len(store.users_by_id) == 1
    assert store.invite(token_hash(raw)).usable()


def test_a_bound_invite_cannot_be_claimed_by_another_email_or_oauth_profile(identity):
    service, store, _, loja, _ = identity
    raw = service.create_invite(loja.id, 'PAID', '  CONVIDADO@EXEMPLO.COM ')
    for kwargs in ({'email': 'outra@exemplo.com', 'password': 'senha-nova-comprida'},
                   {'profile': profile(email='outra@exemplo.com')}):
        with pytest.raises(InviteError, match='e-mail que recebeu'):
            service.accept_invite(raw, **kwargs)
    assert store.invite(token_hash(raw)).usable()
    assert len(store.users_by_id) == 1


def test_existing_account_requires_its_password_and_is_never_reset_by_an_invite(identity):
    service, store, _, _, user = identity
    second = store.create_tenant('segunda-loja', 'Segunda loja')
    raw = service.create_invite(second.id, 'PAID')
    previous_hash = store.password_hash(user.id)
    with pytest.raises(InviteError, match='senha atual'):
        service.accept_invite(raw, email=user.email, password='outra-senha-comprida')
    assert store.membership(user.id, second.id) is None
    assert store.invite(token_hash(raw)).usable()
    assert store.password_hash(user.id) == previous_hash
    _, principal = service.accept_invite(raw, email=user.email, password='senha-bem-comprida')
    assert principal.user.id == user.id
    assert principal.tenant.id == second.id
    assert store.password_hash(user.id) == previous_hash


def test_invite_password_guessing_is_rate_limited(identity):
    service, _, _, loja, user = identity
    raw = service.create_invite(loja.id, 'DEFAULT', user.email)
    for _ in range(5):
        with pytest.raises(InviteError):
            service.accept_invite(raw, password='senha-incorreta')
    with pytest.raises(RateLimited):
        service.accept_invite(raw, password='senha-bem-comprida')


def test_new_invites_validate_the_recipient_and_store(identity):
    service, store, _, loja, _ = identity
    with pytest.raises(InviteError):
        service.create_invite(loja.id, 'DEFAULT', 'sem-email')
    with pytest.raises(InviteError):
        service.create_invite(9999, 'DEFAULT', 'nova@exemplo.com')
    store.suspend(loja.id)
    with pytest.raises(InviteError):
        service.create_invite(loja.id, 'DEFAULT', 'nova@exemplo.com')
    assert store.invites == {}


def test_scrypt_round_trip_and_parameter_upgrade():
    hasher = ScryptHasher(n=2 ** 12)
    encoded = hasher.hash('senha-bem-comprida')
    assert encoded.startswith('scrypt$4096$')
    assert hasher.verify('senha-bem-comprida', encoded)
    assert not hasher.verify('senha-errada', encoded)
    assert not hasher.verify('senha-bem-comprida', 'lixo')
    # Raising the cost must not invalidate stored hashes; it only asks for a rehash.
    assert ScryptHasher(n=2 ** 13).needs_rehash(encoded)
    assert not hasher.needs_rehash(encoded)


# ---- auth_http ---------------------------------------------------------------

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
    from studio_ai.infrastructure.identity.oauth import GoogleOAuthProvider
    from studio_ai.application.identity.model import OAuthProfile
    from studio_ai.presentation.http import cookies
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


# ---- quota -------------------------------------------------------------------

def quota(role='DEFAULT', ledger=None, period='2026-09'):
    return UsageQuota(ledger or MemoryQuotaLedger(), 1, role, lambda: period)


def test_a_default_store_has_a_smaller_allowance_than_a_paid_one():
    assert limits_for('DEFAULT')['campaigns'] < limits_for('PAID')['campaigns']
    # The operator is not metered: metering them protects nobody.
    assert limits_for('OWNER') == {}


def test_reserving_past_the_limit_is_refused_and_names_the_metric():
    allowance = quota()
    limit = limits_for('DEFAULT')['campaigns']
    for _ in range(limit):
        allowance.reserve(campaigns=1)
    with pytest.raises(QuotaError) as refused:
        allowance.reserve(campaigns=1)
    assert refused.value.metric == 'campaigns'
    assert refused.value.limit == limit
    assert refused.value.details()['quota']['used'] == limit


def test_a_partly_fitting_reservation_grants_nothing():
    """Otherwise a carousel that exceeds the image allowance would still burn a campaign."""
    ledger = MemoryQuotaLedger()
    allowance = quota(ledger=ledger)
    with pytest.raises(QuotaError):
        allowance.reserve(campaigns=1, images=limits_for('DEFAULT')['images'] + 1)
    assert ledger.used(1, '2026-09').get('campaigns', 0) == 0


def test_a_voided_ticket_gives_the_units_back():
    ledger = MemoryQuotaLedger()
    ticket = quota(ledger=ledger).reserve(campaigns=1, images=3)
    assert ledger.used(1, '2026-09') == {'campaigns': 1, 'images': 3}
    ticket.void()
    assert ledger.used(1, '2026-09') == {'campaigns': 0, 'images': 0}
    # Voiding twice must not credit the store for work it never did.
    ticket.void()
    assert ledger.used(1, '2026-09') == {'campaigns': 0, 'images': 0}


def test_an_owner_is_counted_but_never_blocked():
    ledger = MemoryQuotaLedger()
    allowance = quota('OWNER', ledger)
    for _ in range(200):
        allowance.reserve(campaigns=1)
    assert ledger.used(1, '2026-09')['campaigns'] == 200
    assert allowance.summary()['metrics']['campaigns']['limit'] is None


def test_the_summary_reports_what_is_left():
    allowance = quota()
    allowance.reserve(campaigns=2, assists=1)
    summary = allowance.summary()
    assert summary['period'] == '2026-09'
    assert summary['metrics']['campaigns']['used'] == 2
    assert summary['metrics']['assists']['used'] == 1
    assert summary['metrics']['images']['used'] == 0


@pytest.fixture
def metered(isolated_root, monkeypatch):
    # A live run is validated against the operator's credentials before the quota gate,
    # so the fixture supplies one; no provider is ever contacted.
    monkeypatch.setenv('OPENAI_API_KEY', 'chave-de-teste')
    monkeypatch.setenv('OPENAI_MODEL', 'gpt-5.6-sol')
    store = FakeIdentityStore()
    service = IdentityService(store, FastHasher(), MemoryRateLimiter())
    loja = store.create_tenant('mercado-central', 'Mercado Central', str(isolated_root))
    user = store.create_user('dono@loja.com.br', 'fake$senha-bem-comprida')
    store.grant(user.id, loja.id, 'DEFAULT')
    ledger = MemoryQuotaLedger()
    identity = Identity(service=service, database=NoDatabase(), providers={}, ledger=ledger)

    server = make_server(isolated_root, 0, identity=identity)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    body = json.dumps({'email': 'dono@loja.com.br', 'password': 'senha-bem-comprida'}).encode()
    response = urlopen(Request(base + '/api/login', data=body, headers={
        'Content-Type': 'application/json', 'Origin': base}))
    jar = SimpleCookie()
    jar.load(response.headers['Set-Cookie'])
    auth = {'Cookie': f'rcs_session={jar["rcs_session"].value}',
            'X-App-Token': json.load(response)['csrf']}
    try:
        yield base, auth, ledger, loja, isolated_root
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)


def test_the_session_reports_the_allowance(metered):
    base, auth, _, _, _ = metered
    session = json.load(urlopen(Request(base + '/api/session', headers={'Cookie': auth['Cookie']})))
    assert session['quota']['metrics']['campaigns']['limit'] == PLANS['DEFAULT']['campaigns']


def test_an_exhausted_allowance_answers_402_and_writes_nothing(metered):
    base, auth, ledger, loja, root = metered
    # Spend the allowance directly, so the test does not depend on running campaigns.
    from studio_ai.infrastructure.identity.quotas import current_period
    ledger.record(loja.id, current_period(), {'campaigns': PLANS['DEFAULT']['campaigns']})
    runs_before = len(list((root / 'campaigns' / 'runs').glob('run-*')))

    data = json.dumps({'request': 'Campanha recusada', 'mode': 'live'}).encode()
    with pytest.raises(HTTPError) as error:
        urlopen(Request(base + '/api/runs', data=data, headers={
            'Content-Type': 'application/json', 'Origin': base, **auth}))
    assert error.value.code == 402
    payload = json.load(error.value)
    assert payload['quota']['metric'] == 'campaigns'
    # The gate runs before create_run, so no directory was left behind.
    assert len(list((root / 'campaigns' / 'runs').glob('run-*'))) == runs_before


def test_a_demo_run_costs_nothing(metered):
    base, auth, ledger, loja, _ = metered
    data = json.dumps({'request': 'Campanha de demonstração', 'mode': 'demo'}).encode()
    assert json.load(urlopen(Request(base + '/api/runs', data=data, headers={
        'Content-Type': 'application/json', 'Origin': base, **auth})))['id']
    from studio_ai.infrastructure.identity.quotas import current_period
    assert ledger.used(loja.id, current_period()).get('campaigns', 0) == 0
