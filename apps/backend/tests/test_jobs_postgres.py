"""The durable queue. Skipped without TEST_DATABASE_URL, like the other Postgres tests."""
import os
import uuid

import pytest

URL = os.environ.get('TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='TEST_DATABASE_URL não configurada')


@pytest.fixture
def queue():
    from realcenter_marketing.infrastructure.identity.database import Database
    from realcenter_marketing.infrastructure.identity.jobs import PostgresJobQueue
    from realcenter_marketing.infrastructure.identity.store import PostgresIdentityStore
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
    from realcenter_marketing.infrastructure.identity.jobs import PostgresJobQueue
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
