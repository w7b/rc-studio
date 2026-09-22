"""Real HTTP admission and a separate worker registry sharing Postgres and disk."""
import json
import os
import threading
import uuid
from urllib.request import Request, urlopen

import pytest

from script_loader import load_script
from test_auth_http import sign_in
from realcenter_marketing.bootstrap.platform import build_identity
from realcenter_marketing.bootstrap.registry import TenantRegistry
from realcenter_marketing.infrastructure.identity.database import Database
from realcenter_marketing.infrastructure.identity.jobs import PostgresJobQueue
from realcenter_marketing.infrastructure.identity.passwords import ScryptHasher
from realcenter_marketing.presentation.http.server import make_server

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
