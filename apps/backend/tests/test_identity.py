"""Rules that decide who gets in, and on behalf of which store."""
from datetime import timedelta

import pytest

from identity_fake import FakeIdentityStore
from realcenter_marketing.application.identity.errors import AccountError, AuthError, InviteError, NoAccess, RateLimited
from realcenter_marketing.application.identity.model import ABSOLUTE_LIFETIME, IDLE_LIFETIME, OAuthProfile, now
from realcenter_marketing.application.identity.service import IdentityService, token_hash
from realcenter_marketing.infrastructure.identity.passwords import ScryptHasher
from realcenter_marketing.infrastructure.identity.rate_limit import MemoryRateLimiter


class FastHasher:
    """The scrypt parameters are deliberately expensive; the rules do not need them."""

    def __init__(self):
        self.dummies = 0

    def hash(self, password):
        return 'fake$' + password

    def verify(self, password, encoded):
        return encoded == 'fake$' + password

    def dummy_verify(self):
        self.dummies += 1


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


# -- OAuth2 -------------------------------------------------------------------

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


# -- invites ------------------------------------------------------------------

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


# -- password hashing ---------------------------------------------------------

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
