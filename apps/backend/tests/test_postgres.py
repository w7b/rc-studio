"""Tudo que exige Postgres. Pulado sem TEST_DATABASE_URL."""
import json
import os
import threading
import uuid
from urllib.request import Request, urlopen
import pytest
from script_loader import load_script
from test_identity import sign_in
from studio_ai.bootstrap.platform import build_identity
from studio_ai.bootstrap.registry import TenantRegistry
from studio_ai.infrastructure.identity.database import Database
from studio_ai.infrastructure.identity.jobs import PostgresJobQueue
from studio_ai.infrastructure.identity.passwords import ScryptHasher
from studio_ai.presentation.http.server import make_server
from datetime import timedelta
from studio_ai.application.identity.model import now
from concurrent.futures import ThreadPoolExecutor
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from studio_ai.infrastructure.identity.database import Database, SCHEMA


# ---- durable_execution -------------------------------------------------------

URL = os.environ.get('TEST_DATABASE_URL')


pytestmark = pytest.mark.skipif(not URL, reason='TEST_DATABASE_URL não configurada')


worker = load_script('worker')


@pytest.fixture
def durable(isolated_root):
    identity = build_identity(URL)
    store = identity.service.store
    suffix = uuid.uuid4().hex
    tenant = store.create_tenant('durable-' + suffix, 'Durable', str(isolated_root))
    email, password = f'durable-{suffix}@test.invalid', 'dedicated-test-password'
    user = store.create_user(email, ScryptHasher().hash(password), 'Tester')
    store.grant(user.id, tenant.id, 'DEFAULT')
    server = make_server(isolated_root, 0, identity=identity)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    cookie, csrf, _ = sign_in(base, email, password)
    closed = False
    def close_web():
        nonlocal closed
        if not closed:
            server.shutdown()
            server.server_close()
            thread.join(2)
            closed = True
    database = Database(URL).open()
    registry = TenantRegistry(isolated_root / 'tenants', quota_for=None, queue_for=None)
    try:
        yield server, base, cookie, csrf, PostgresJobQueue(database), registry, tenant, close_web
    finally:
        close_web()
        registry.close()
        with database.connection() as connection, connection.cursor() as cursor:
            cursor.execute('DELETE FROM users WHERE id = %s', (user.id,))
            cursor.execute('DELETE FROM tenants WHERE id = %s', (tenant.id,))
        database.close()


def admit(durable):
    server, base, cookie, csrf, queue, registry, tenant, close_web = durable
    body = json.dumps({'request': 'Campanha persistente', 'mode': 'demo'}).encode()
    with urlopen(Request(base + '/api/runs', data=body, headers={
            'Content-Type': 'application/json', 'Origin': base,
            'Cookie': cookie, 'X-App-Token': csrf})) as response:
        assert response.status == 202
        run_id = json.load(response)['id']
    with urlopen(Request(base + '/api/runs', headers={'Cookie': cookie})) as response:
        state = json.load(response)
    assert state['active_id'] == run_id and state['busy']
    assert state['runs'][0]['status'] == 'queued'
    assert not state['runs'][0]['outputs'].get('campaign')
    assert queue.pending(tenant.id) == 1
    return run_id


def test_http_to_queue_to_worker_to_result(durable):
    _, base, cookie, _, queue, registry, tenant, _ = durable
    run_id = admit(durable)
    assert worker.run_once(registry, queue)
    with urlopen(Request(base + '/api/runs', headers={'Cookie': cookie})) as response:
        state = json.load(response)
    assert state['runs'][0]['id'] == run_id
    assert state['runs'][0]['status'] == 'completed'
    assert state['runs'][0]['outputs']['campaign']
    assert state['active_id'] is None and not state['busy']
    assert queue.pending(tenant.id) == 0


def test_closing_web_process_does_not_lose_campaign(durable):
    _, _, _, _, queue, registry, tenant, close_web = durable
    run_id = admit(durable)
    close_web()
    assert queue.pending(tenant.id) == 1
    assert worker.run_once(registry, queue)
    context = registry.context(tenant.slug, tenant.root_path, tenant_id=tenant.id, role='OWNER')
    assert context.service.repository.last_event(run_id) == 'run_completed'
    assert context.service.repository.has_campaign(run_id)
    assert queue.pending(tenant.id) == 0


# ---- identity_postgres -------------------------------------------------------

@pytest.fixture
def store():
    """Rows created here are removed afterwards.

    TEST_DATABASE_URL may well point at a database someone is also using by hand, and
    leaving `loja-4f5501f176` rows behind turns their admin panel into a junk drawer.
    """
    from studio_ai.infrastructure.identity.database import Database
    from studio_ai.infrastructure.identity.store import PostgresIdentityStore
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


# ---- jobs_postgres -----------------------------------------------------------

@pytest.fixture
def queue():
    from studio_ai.infrastructure.identity.database import Database
    from studio_ai.infrastructure.identity.jobs import PostgresJobQueue
    from studio_ai.infrastructure.identity.store import PostgresIdentityStore
    database = Database(URL, min_size=1, max_size=4).open()
    store = PostgresIdentityStore(database)
    tenant = store.create_tenant(f'fila-{uuid.uuid4().hex[:8]}', 'Loja da Fila')
    try:
        yield PostgresJobQueue(database), tenant
    finally:
        try:
            with database.connection() as connection, connection.cursor() as cursor:
                cursor.execute('DELETE FROM jobs WHERE tenant_id = %s', (tenant.id,))
                cursor.execute('DELETE FROM tenants WHERE id = %s', (tenant.id,))
        finally:
            database.close()


def test_a_job_is_claimed_once_and_only_once(queue):
    jobs, tenant = queue
    jobs.enqueue(tenant.id, tenant.slug, None, 'campaign', {'request': 'Teste', 'mode': 'demo'})
    first = jobs.claim()
    assert first is not None and first['kind'] == 'campaign'
    assert first['payload']['request'] == 'Teste'
    # Claiming marks it running, so a second worker must not receive the same row.
    assert all(job is None or job['id'] != first['id'] for job in [jobs.claim()])
    jobs.finish(first['id'])
    assert jobs.pending(tenant.id) == 0


def test_a_failed_job_records_its_error(queue):
    jobs, tenant = queue
    job_id = jobs.enqueue(tenant.id, tenant.slug, None, 'image', {}, run_id='run-' + 'a' * 32)
    claimed = jobs.claim()
    assert claimed['id'] == job_id
    jobs.finish(job_id, error='OSError: disco cheio')
    with jobs.database.connection() as connection, connection.cursor() as cursor:
        cursor.execute('SELECT status, last_error, attempts FROM jobs WHERE id = %s', (job_id,))
        status, error, attempts = cursor.fetchone()
    assert (status, attempts) == ('failed', 1)
    assert 'disco cheio' in error


def test_a_worker_killed_mid_job_has_its_work_put_back(queue):
    """Without this a crashed worker leaves the row 'running' forever and nobody ever
    picks it up again — the campaign simply disappears."""
    jobs, tenant = queue
    job_id = jobs.enqueue(tenant.id, tenant.slug, None, 'campaign', {'mode': 'demo'})
    jobs.claim()
    with jobs.database.connection() as connection, connection.cursor() as cursor:
        cursor.execute("UPDATE jobs SET claimed_at = now() - interval '3 hours' WHERE id = %s", (job_id,))
    assert jobs.requeue_stale(older_than_seconds=60) == 1
    recovered = jobs.claim()
    assert recovered['id'] == job_id
    jobs.finish(job_id)


def test_pending_counts_queued_and_running(queue):
    jobs, tenant = queue
    assert jobs.pending(tenant.id) == 0
    jobs.enqueue(tenant.id, tenant.slug, None, 'campaign', {})
    jobs.enqueue(tenant.id, tenant.slug, None, 'campaign', {})
    assert jobs.pending(tenant.id) == 2
    claimed = jobs.claim()
    assert jobs.pending(tenant.id) == 2
    jobs.finish(claimed['id'])
    assert jobs.pending(tenant.id) == 1


def test_stolen_lease_cannot_be_finished_or_heartbeated_by_old_owner(queue):
    from studio_ai.infrastructure.identity.jobs import PostgresJobQueue
    jobs, tenant = queue
    job_id = jobs.enqueue(tenant.id, tenant.slug, None, 'campaign', {})
    jobs.claim()
    jobs.requeue_stale(older_than_seconds=-1)
    other = PostgresJobQueue(jobs.database)
    assert other.claim()['id'] == job_id
    assert not jobs.finish(job_id)
    assert not jobs.heartbeat(job_id)
    assert not jobs.requeue(job_id)
    assert other.pending(tenant.id) == 1
    assert other.finish(job_id)


def test_heartbeat_extends_lease_and_active_is_tenant_scoped(queue):
    jobs, tenant = queue
    job_id = jobs.enqueue(tenant.id, tenant.slug, None, 'campaign', {}, 'run-test')
    assert jobs.active(tenant.id) == [{'id': job_id, 'run_id': 'run-test', 'status': 'queued'}]
    jobs.claim()
    with jobs.database.connection() as connection, connection.cursor() as cursor:
        cursor.execute("UPDATE jobs SET claimed_at = now() - interval '1 hour' WHERE id = %s", (job_id,))
    assert jobs.heartbeat(job_id)
    assert jobs.requeue_stale() == 0
    assert jobs.active(tenant.id)[0]['status'] == 'running'
    assert jobs.active(-1) == []
    jobs.finish(job_id)
    assert jobs.active(tenant.id) == []


def test_exhausted_crashes_are_terminal_but_busy_does_not_spend_attempt(queue):
    jobs, tenant = queue
    job_id = jobs.enqueue(tenant.id, tenant.slug, None, 'campaign', {})
    jobs.claim()
    assert jobs.requeue(job_id)
    for _ in range(3):
        assert jobs.claim()['id'] == job_id
        jobs.requeue_stale(older_than_seconds=-1)
    assert jobs.claim() is None
    assert jobs.abandon_exhausted() == 1
    assert jobs.pending(tenant.id) == 0
    with jobs.database.connection() as connection, connection.cursor() as cursor:
        cursor.execute('SELECT status, attempts, last_error FROM jobs WHERE id = %s', (job_id,))
        status, attempts, error = cursor.fetchone()
    assert (status, attempts) == ('failed', 3)
    assert 'tentativas' in error


# ---- schema_migrations -------------------------------------------------------

@pytest.fixture
def migration_url():
    schema = 'migration_' + uuid.uuid4().hex
    with psycopg.connect(URL, autocommit=True) as connection:
        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    try:
        yield make_conninfo(URL, options=f'-c search_path={schema}')
    finally:
        with psycopg.connect(URL, autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def test_fresh_database_records_versions_only_once(migration_url):
    database = Database(migration_url).open()
    try:
        with database.connection() as connection:
            before = connection.execute('SELECT version, applied_at FROM schema_migrations ORDER BY version').fetchall()
        database.apply_schema()
        with database.connection() as connection:
            after = connection.execute('SELECT version, applied_at FROM schema_migrations ORDER BY version').fetchall()
            connection.execute('SELECT heartbeat_at FROM jobs')
        assert before == after
        assert [row[0] for row in before] == ['001_baseline', '002_membership_roles']
    finally:
        database.close()


def test_legacy_role_constraint_and_existing_rows_are_migrated(migration_url):
    with psycopg.connect(migration_url, autocommit=True) as connection:
        legacy = SCHEMA.read_text(encoding='utf-8').replace("'DEFAULT', 'PAID', 'OWNER'", "'owner', 'manager', 'editor'")
        connection.execute(legacy)
        tenant = connection.execute("INSERT INTO tenants (slug, name) VALUES ('legacy', 'Legacy') RETURNING id").fetchone()[0]
        for role in ('owner', 'manager', 'editor'):
            user = connection.execute('INSERT INTO users (email) VALUES (%s) RETURNING id', (role + '@test.invalid',)).fetchone()[0]
            connection.execute('INSERT INTO memberships VALUES (%s, %s, %s)', (user, tenant, role))
            connection.execute('INSERT INTO sessions (token_hash, user_id, tenant_id, role, csrf) VALUES (%s,%s,%s,%s,%s)',
                               (role, user, tenant, role, 'csrf'))
            connection.execute("INSERT INTO invites (token_hash, tenant_id, role, expires_at) VALUES (%s,%s,%s,now() + interval '1 day')",
                               (role, tenant, role))
    database = Database(migration_url).open()
    try:
        with database.connection() as connection:
            for table in ('memberships', 'sessions', 'invites'):
                roles = connection.execute(sql.SQL('SELECT role FROM {} ORDER BY role').format(sql.Identifier(table))).fetchall()
                assert roles == [('DEFAULT',), ('OWNER',), ('PAID',)]
            connection.execute("UPDATE memberships SET role = 'PAID'")
            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute("UPDATE memberships SET role = 'editor'")
    finally:
        database.close()


def test_concurrent_boots_apply_each_migration_once(migration_url):
    def boot(_):
        database = Database(migration_url).open()
        database.close()
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(boot, range(2)))
    with psycopg.connect(migration_url) as connection:
        assert connection.execute('SELECT count(*) FROM schema_migrations').fetchone()[0] == 2


def test_failed_migration_rolls_back_schema_and_version(migration_url, tmp_path, monkeypatch):
    import studio_ai.infrastructure.identity.database as module
    migrations = tmp_path / 'migrations'
    migrations.mkdir()
    (migrations / '001_broken.sql').write_text('CREATE TABLE should_rollback (id integer); SELECT missing_column;', encoding='utf-8')
    monkeypatch.setattr(module, 'MIGRATIONS', migrations, raising=False)
    database = Database(migration_url)
    try:
        with pytest.raises(psycopg.errors.UndefinedColumn):
            database.open()
        with psycopg.connect(migration_url) as connection:
            assert connection.execute("SELECT to_regclass('should_rollback')").fetchone()[0] is None
            if connection.execute("SELECT to_regclass('schema_migrations')").fetchone()[0]:
                assert connection.execute('SELECT count(*) FROM schema_migrations').fetchone()[0] == 0
    finally:
        database.close()
