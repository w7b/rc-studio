"""Contract tests for the Postgres adapter.

Skipped unless TEST_DATABASE_URL points at a disposable server, so the default suite and
the network-disabled container smoke keep working without a database:

    docker run --rm -e POSTGRES_PASSWORD=studio -p 5433:5432 postgres:17-alpine
    TEST_DATABASE_URL=postgresql://postgres:studio@127.0.0.1:5433/postgres python -m pytest
"""
import os
import uuid
from datetime import timedelta

import pytest

from realcenter_marketing.application.identity.model import now

URL = os.environ.get('TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='TEST_DATABASE_URL não configurada')


@pytest.fixture
def store():
    """Rows created here are removed afterwards.

    TEST_DATABASE_URL may well point at a database someone is also using by hand, and
    leaving `loja-4f5501f176` rows behind turns their admin panel into a junk drawer.
    """
    from realcenter_marketing.infrastructure.identity.database import Database
    from realcenter_marketing.infrastructure.identity.store import PostgresIdentityStore
    database = Database(URL, min_size=1, max_size=4).open()
    try:
        yield PostgresIdentityStore(database)
    finally:
        try:
            with database.connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM users WHERE id IN (SELECT m.user_id FROM memberships m "
                    "JOIN tenants t ON t.id = m.tenant_id WHERE t.slug LIKE 'loja-%%' "
                    "OR t.slug LIKE 'pessoa-%%')")
                cursor.execute("DELETE FROM users WHERE email LIKE 'dono-%%' OR email LIKE 'pessoa-%%'")
                cursor.execute("DELETE FROM tenants WHERE slug LIKE 'loja-%%'")
        finally:
            database.close()


def unique(prefix):
    return f'{prefix}-{uuid.uuid4().hex[:10]}'


def test_schema_is_idempotent(store):
    # Boot applies only pending migrations; repeating it must be harmless.
    store.database.apply_schema()
    store.database.apply_schema()
    assert store.tenants() is not None


def test_tenant_user_membership_round_trip(store):
    tenant = store.create_tenant(unique('loja'), 'Loja de Teste', '/dados/loja')
    assert store.tenant(tenant.id) == tenant
    assert store.tenant_by_slug(tenant.slug) == tenant
    assert tenant.root_path == '/dados/loja'

    email = f'{unique("dono")}@loja.com.br'
    user = store.create_user(email, 'scrypt$1$2$3$x$y', 'Dono')
    assert store.user_by_id(user.id) == user
    # Addresses are matched without regard to case, so one person cannot hold two rows.
    assert store.user_by_email(email.upper()) == user
    assert store.password_hash(user.id) == 'scrypt$1$2$3$x$y'

    store.grant(user.id, tenant.id, 'OWNER')
    assert store.membership(user.id, tenant.id) == 'OWNER'
    assert (tenant, 'OWNER') in store.memberships(user.id)
    # Granting twice updates the role instead of failing.
    store.grant(user.id, tenant.id, 'DEFAULT')
    assert store.membership(user.id, tenant.id) == 'DEFAULT'


def test_identity_is_keyed_on_subject_not_on_email(store):
    tenant = store.create_tenant(unique('loja'), 'Loja')
    user = store.create_user(f'{unique("pessoa")}@gmail.com', None)
    store.grant(user.id, tenant.id, 'OWNER')
    subject = unique('google-sub')
    store.link_identity(user.id, 'google', subject)
    assert store.user_by_identity('google', subject) == user
    # Re-linking the same subject is an update, never a duplicate row.
    store.link_identity(user.id, 'google', subject)
    assert store.user_by_identity('google', subject) == user
    assert store.user_by_identity('google', unique('outro')) is None


def test_sessions_are_created_touched_and_dropped(store):
    tenant = store.create_tenant(unique('loja'), 'Loja')
    user = store.create_user(f'{unique("pessoa")}@loja.com.br', 'x')
    store.grant(user.id, tenant.id, 'OWNER')
    token = unique('hash')
    session = store.create_session(token, user.id, tenant.id, 'OWNER', 'csrf-token')
    assert session.csrf == 'csrf-token'
    assert store.session(token).user_id == user.id
    store.touch_session(token)
    assert store.session(token).last_seen_at >= session.last_seen_at
    store.drop_session(token)
    assert store.session(token) is None

    for _ in range(3):
        store.create_session(unique('hash'), user.id, tenant.id, 'OWNER', 'c')
    store.drop_user_sessions(user.id)
    assert store.memberships(user.id)  # membership survives; only sessions are cleared


def test_an_invite_can_only_be_claimed_once(store):
    tenant = store.create_tenant(unique('loja'), 'Loja')
    token = unique('convite')
    store.create_invite(token, tenant.id, 'DEFAULT', 'novo@loja.com.br', now() + timedelta(days=7))
    assert store.invite(token).usable()
    # The conditional update is the claim: a second opener of the same link loses.
    assert store.consume_invite(token) is True
    assert store.consume_invite(token) is False
    assert not store.invite(token).usable()
