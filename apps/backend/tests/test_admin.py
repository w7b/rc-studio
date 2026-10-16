"""Painel administrativo, métricas e logs."""
import json
import threading
from http.cookies import SimpleCookie
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import pytest
from identity_fake import FakeIdentityStore
from studio_ai.application.identity.errors import AdminError
from studio_ai.application.identity.model import ROLES
from studio_ai.application.identity.service import IdentityService
from studio_ai.bootstrap.platform import Identity
from studio_ai.infrastructure.identity.rate_limit import MemoryRateLimiter
from studio_ai.presentation.http.server import make_server
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from studio_ai.infrastructure.admin_metrics import collect_metrics
from studio_ai.infrastructure.observability.journal import RunJournal
from studio_ai.infrastructure.logs import usage_audit, system_activity


# ---- admin -------------------------------------------------------------------

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
def panel(isolated_root):
    store = FakeIdentityStore()
    service = IdentityService(store, FastHasher(), MemoryRateLimiter())
    loja = store.create_tenant('mercado-central', 'Mercado Central')
    for email, role in (('dono@plataforma.com.br', 'OWNER'),
                        ('pagante@loja.com.br', 'PAID'),
                        ('comum@loja.com.br', 'DEFAULT')):
        user = store.create_user(email, 'fake$senha-bem-comprida')
        store.grant(user.id, loja.id, role)

    identity = Identity(service=service, database=NoDatabase(), providers={})
    server = make_server(isolated_root, 0, identity=identity)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        yield base, store, service, {email: sign_in(base, email)
                                     for email in ('dono@plataforma.com.br',
                                                   'pagante@loja.com.br', 'comum@loja.com.br')}
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


def post(base, path, payload, auth):
    return urlopen(Request(base + path, data=json.dumps(payload).encode(), headers={
        'Content-Type': 'application/json', 'Origin': base, **auth}))


def test_the_three_roles_are_the_declared_ones():
    assert ROLES == ('DEFAULT', 'PAID', 'OWNER')


def test_model_credentials_are_owner_only_write_only_and_isolated(panel):
    base, store, _, auth = panel
    tenant = store.tenants()[0]
    path = '/api/admin/tenants/model-keys'
    payload = {'tenant_id': tenant.id, 'changes': {'openai': {'action': 'replace', 'key': 'fixture-secret-key'}}}
    for email in ('pagante@loja.com.br', 'comum@loja.com.br'):
        with pytest.raises(HTTPError) as error:
            post(base, path, payload, auth[email])
        assert error.value.code == 403
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + path + f'?tenant_id={tenant.id}', headers=auth[email]))
        assert error.value.code == 403
    owner = auth['dono@plataforma.com.br']
    result = json.load(post(base, path, payload, owner))
    assert result['providers']['openai']['source'] == 'store'
    assert 'fixture-secret-key' not in json.dumps(result)
    other = store.create_tenant('outra-loja', 'Outra loja')
    other_keys = json.load(urlopen(Request(base + path + f'?tenant_id={other.id}', headers=owner)))
    assert other_keys['providers']['openai']['source'] != 'store'
    loaded = json.load(urlopen(Request(base + path + f'?tenant_id={tenant.id}', headers=owner)))
    assert 'fixture-secret-key' not in json.dumps(loaded)
    json.load(post(base, path, {'tenant_id': tenant.id, 'changes': {'openai': {'action': 'inherit'}}}, owner))
    loaded = json.load(urlopen(Request(base + path + f'?tenant_id={tenant.id}', headers=owner)))
    assert loaded['providers']['openai']['source'] != 'store'


def test_metrics_and_module_management_are_owner_only(panel):
    base, store, _, auth = panel
    tenant = store.tenants()[0]
    for email in ('pagante@loja.com.br', 'comum@loja.com.br'):
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + '/api/admin/metrics', headers=auth[email]))
        assert error.value.code == 403
        with pytest.raises(HTTPError) as error:
            post(base, '/api/admin/tenants/modules', {'tenant_id': tenant.id, 'module': 'campaigns', 'enabled': False}, auth[email])
        assert error.value.code == 403
    metrics = json.load(urlopen(Request(base + '/api/admin/metrics', headers=auth['dono@plataforma.com.br'])))
    assert metrics['periods']['all']['new_stores'] == 1
    assert metrics['periods']['all']['new_users'] == 3


def test_disabling_modules_blocks_direct_api_access_and_preserves_account(panel):
    base, store, _, auth = panel
    tenant = store.tenants()[0]
    owner, member = auth['dono@plataforma.com.br'], auth['pagante@loja.com.br']
    # References ride with the Library and the consultancy rides with Meta Ads, so one
    # switch governs each pair instead of two that only made sense together.
    for module, read, write in [('campaigns', '/api/runs', '/api/brief-assist'),
                                ('art_lib', '/api/references', '/api/references'),
                                ('meta_ads', None, '/api/consultations')]:
        post(base, '/api/admin/tenants/modules', {'tenant_id': tenant.id, 'module': module, 'enabled': False}, owner)
        if read:
            with pytest.raises(HTTPError) as error:
                urlopen(Request(base + read, headers=member))
            assert error.value.code == 403
        with pytest.raises(HTTPError) as error:
            post(base, write, {}, member)
        assert error.value.code == 403
    for path in ('/api/media/unknown/delete', '/api/references/unknown/delete'):
        with pytest.raises(HTTPError) as error:
            post(base, path, {}, member)
        assert error.value.code == 403
    assert urlopen(Request(base + '/api/store', headers=member)).status == 200
    session = json.load(urlopen(Request(base + '/api/session', headers=member)))
    assert session['modules']['campaigns'] is False
    with pytest.raises(HTTPError) as error:
        post(base, '/api/integrations', {'module': 'meta_ads', 'values': {'enabled': True}}, member)
    assert error.value.code == 403
    post(base, '/api/admin/tenants/modules', {'tenant_id': tenant.id, 'module': 'campaigns', 'enabled': True}, owner)
    assert urlopen(Request(base + '/api/runs', headers=member)).status == 200


def test_module_changes_are_tenant_scoped_and_strictly_validated(panel):
    base, store, _, auth = panel
    tenant = store.tenants()[0]
    other = store.create_tenant('outra-loja', 'Outra loja')
    owner = auth['dono@plataforma.com.br']
    post(base, '/api/admin/tenants/modules', {'tenant_id': tenant.id, 'module': 'erp', 'enabled': False}, owner)
    assert store.modules(other.id)['erp'] is True
    for module, enabled in [('erp', 'false'), ('account', False), ('unknown', True)]:
        with pytest.raises(HTTPError) as error:
            post(base, '/api/admin/tenants/modules', {'tenant_id': tenant.id, 'module': module, 'enabled': enabled}, owner)
        assert error.value.code == 400


def test_only_the_owner_reaches_the_panel(panel):
    base, _, _, auth = panel
    assert json.load(urlopen(Request(base + '/api/admin/overview',
                                     headers={'Cookie': auth['dono@plataforma.com.br']['Cookie']})))['tenants']
    # Paying is not the same as administering — this is the line that must not blur.
    for email in ('pagante@loja.com.br', 'comum@loja.com.br'):
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + '/api/admin/overview', headers={'Cookie': auth[email]['Cookie']}))
        assert error.value.code == 403, email


def test_a_non_owner_cannot_write_through_the_panel(panel):
    base, store, _, auth = panel
    for email in ('pagante@loja.com.br', 'comum@loja.com.br'):
        with pytest.raises(HTTPError) as error:
            post(base, '/api/admin/tenants', {'slug': 'invadida', 'name': 'Invadida'}, auth[email])
        assert error.value.code == 403, email
    assert store.tenant_by_slug('invadida') is None


def test_the_owner_creates_a_store_and_sees_it_in_the_overview(panel):
    base, _, _, auth = panel
    created = json.load(post(base, '/api/admin/tenants',
                             {'slug': 'petshop-amigo', 'name': 'Petshop Amigo'},
                             auth['dono@plataforma.com.br']))
    assert created['slug'] == 'petshop-amigo'
    overview = json.load(urlopen(Request(base + '/api/admin/overview',
                                         headers={'Cookie': auth['dono@plataforma.com.br']['Cookie']})))
    assert {t['slug'] for t in overview['tenants']} == {'mercado-central', 'petshop-amigo'}


def test_a_slug_is_validated_and_never_duplicated(panel):
    base, _, _, auth = panel
    owner = auth['dono@plataforma.com.br']
    for slug in ('Loja Com Espaco', '../fuga', ''):
        with pytest.raises(HTTPError) as error:
            post(base, '/api/admin/tenants', {'slug': slug, 'name': 'Qualquer'}, owner)
        assert error.value.code == 400, slug
    with pytest.raises(HTTPError) as error:
        post(base, '/api/admin/tenants', {'slug': 'mercado-central', 'name': 'Outra'}, owner)
    assert error.value.code == 400


def test_changing_a_role_ends_the_open_sessions_of_that_user(panel):
    base, store, _, auth = panel
    loja = store.tenant_by_slug('mercado-central')
    comum = store.user_by_email('comum@loja.com.br')

    post(base, '/api/admin/memberships',
         {'user_id': comum.id, 'tenant_id': loja.id, 'role': 'PAID'},
         auth['dono@plataforma.com.br'])
    assert store.membership(comum.id, loja.id) == 'PAID'
    # The role travels inside the session, so an open one would keep the old powers.
    assert json.load(urlopen(Request(base + '/api/session',
                                     headers={'Cookie': auth['comum@loja.com.br']['Cookie']})))['authenticated'] is False


def test_revoking_access_locks_the_user_out_immediately(panel):
    base, store, _, auth = panel
    loja = store.tenant_by_slug('mercado-central')
    pagante = store.user_by_email('pagante@loja.com.br')

    post(base, '/api/admin/memberships/revoke', {'user_id': pagante.id, 'tenant_id': loja.id},
         auth['dono@plataforma.com.br'])
    with pytest.raises(HTTPError) as error:
        urlopen(Request(base + '/api/runs', headers={'Cookie': auth['pagante@loja.com.br']['Cookie']}))
    assert error.value.code == 401


def test_suspending_a_store_drops_every_session_it_had(panel):
    base, store, _, auth = panel
    loja = store.tenant_by_slug('mercado-central')
    post(base, '/api/admin/tenants/status', {'tenant_id': loja.id, 'status': 'suspended'},
         auth['dono@plataforma.com.br'])
    for email in ('pagante@loja.com.br', 'comum@loja.com.br'):
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + '/api/runs', headers={'Cookie': auth[email]['Cookie']}))
        assert error.value.code == 401, email


def test_the_invite_link_is_returned_once_and_carries_the_token_in_the_fragment(panel):
    base, store, _, auth = panel
    loja = store.tenant_by_slug('mercado-central')
    link = json.load(post(base, '/api/admin/invites',
                          {'tenant_id': loja.id, 'role': 'PAID', 'email': 'novo@loja.com.br'},
                          auth['dono@plataforma.com.br']))['link']
    # The fragment never reaches a server, so the token stays out of proxy logs.
    assert '/convite#' in link
    assert len(store.invites) == 1


def test_an_unknown_role_is_refused(panel):
    base, store, service, auth = panel
    loja = store.tenant_by_slug('mercado-central')
    comum = store.user_by_email('comum@loja.com.br')
    with pytest.raises(HTTPError) as error:
        post(base, '/api/admin/memberships',
             {'user_id': comum.id, 'tenant_id': loja.id, 'role': 'ADMINISTRADOR'},
             auth['dono@plataforma.com.br'])
    assert error.value.code == 400
    assert store.membership(comum.id, loja.id) == 'DEFAULT'

    with pytest.raises(AdminError):
        service.set_role(comum.id, loja.id, 'root')


# ---- admin_metrics -----------------------------------------------------------

def journal(root, name, date, *, assist=False, entries=None, unknown=False):
    path = root / 'campaigns' / ('brief-assists' if assist else 'runs') / name
    path.mkdir(parents=True)
    (path / 'events.jsonl').write_text(json.dumps({'time': date, 'event': 'assist_completed' if assist else 'run_completed'}) + '\n{partial', encoding='utf-8')
    data = {'text': {'requests': 2, 'input_tokens': 100, 'output_tokens': 30, 'cost_usd': None if unknown else .2},
            'image': {'count': 1, 'cost_usd': .1}}
    if entries is not None:
        data['entries'] = entries
    (path / 'usage.json').write_text(json.dumps(data), encoding='utf-8')
    return path


def test_periods_use_all_stores_timezone_boundaries_and_unknown_cost(tmp_path):
    store = FakeIdentityStore()
    a = store.create_tenant('alpha', 'Alpha')
    b = store.create_tenant('beta', 'Beta')
    now = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
    store.created_stores[a.id] = now - timedelta(days=1)
    store.created_stores[b.id] = now - timedelta(days=50)
    journal(tmp_path / 'alpha', 'run-recent', '2026-09-18T12:00:00Z')
    journal(tmp_path / 'beta', 'run-month', '2026-09-02T12:00:00Z', unknown=True)
    # Sep 1 UTC is still August in Brazil.
    journal(tmp_path / 'beta', 'run-old', '2026-09-01T01:00:00Z', assist=True)
    report = collect_metrics(store, lambda slug, _: tmp_path / slug, now)
    week, month, all_time = (report['periods'][p] for p in ('week', 'month', 'all'))
    assert week['requests'] == 3 and week['new_stores'] == 1
    assert month['requests'] == 6 and month['unpriced_records'] == 1
    assert month['known_cost_usd'] == pytest.approx(.4)
    assert all_time['requests'] == 9 and all_time['new_stores'] == 2
    assert all_time['active_stores'] == 2 and all_time['brief_assists'] == 1
    assert len(report['daily']) == 30


def test_timestamped_entries_count_later_images_without_double_counting_snapshots(tmp_path):
    store = FakeIdentityStore()
    store.create_tenant('alpha', 'Alpha')
    journal(tmp_path, 'run-old', '2026-08-01T00:00:00Z', entries=[
        {'time': '2026-09-18T12:00:00Z', 'requests': 1, 'images': 1, 'known_cost_usd': .1}])
    result = collect_metrics(store, lambda *_: tmp_path, datetime(2026, 9, 19, tzinfo=timezone.utc))['periods']['week']
    assert result['campaigns'] == 0 and result['images'] == 1 and result['requests'] == 1
    assert result['known_cost_usd'] == .1 and result['legacy_records'] == 0


def test_undated_legacy_usage_only_enters_general_totals(tmp_path):
    store = FakeIdentityStore()
    store.create_tenant('alpha', 'Alpha')
    journal(tmp_path, 'run-undated', None)
    report = collect_metrics(store, lambda *_: tmp_path)
    assert report['periods']['week']['requests'] == 0
    assert report['periods']['all']['undated_records'] == 1


def test_resuming_a_legacy_journal_preserves_old_usage_once(tmp_path):
    directory = journal(tmp_path, 'run-old', '2026-09-01T12:00:00Z')
    # Use the full historical schema before resuming image generation.
    old = json.loads((directory / 'usage.json').read_text())
    old['text']['by_agent'] = {}
    (directory / 'usage.json').write_text(json.dumps(old))
    current = RunJournal.resume(directory)
    current.record_image_usage('unpriced-model')
    current.record_image_usage('unpriced-model')
    data = json.loads((directory / 'usage.json').read_text())
    assert len(data['entries']) == 3
    assert data['entries'][0]['legacy'] is True
    assert sum(row['requests'] for row in data['entries']) == 5
    assert data['entries'][-1]['unpriced_records'] == 1


# ---- logs --------------------------------------------------------------------

def test_usage_includes_assists_and_activity_redacts(tmp_path):
    for folder in ('runs/run-'+'a'*32, 'brief-assists/test'):
        d=tmp_path/'campaigns'/folder; d.mkdir(parents=True)
        (d/'usage.json').write_text(json.dumps({'text':{'model':'test','by_agent':{'Director':{'requests':1,'input_tokens':10,'output_tokens':2}}}}))
        (d/'events.jsonl').write_text(json.dumps({'event':'response_received','time':'2026-09-10','secret':'hidden'})+'\n{partial')
    result=usage_audit(tmp_path)
    assert result['input_tokens']==20 and result['output_tokens']==4
    assert result['record_count']==2
    assert 'hidden' not in json.dumps(system_activity(tmp_path))


def test_snapshot_is_memoised_until_the_run_directory_changes(root):
    """The frontend polls this every two seconds per tab. Re-reading every events.jsonl
    each time is what gives way first under load — before campaign execution does."""
    from studio_ai.infrastructure.persistence import filesystem

    runs = root / 'campaigns' / 'runs' / ('run-' + 'a' * 32)
    runs.mkdir(parents=True)
    (runs / 'events.jsonl').write_text('{"event": "run_completed", "time": "2026-09-19T10:00:00"}\n',
                                       encoding='utf-8')

    reads = {'count': 0}
    original = filesystem.media_catalog

    def counting(value):
        reads['count'] += 1
        return original(value)

    filesystem.media_catalog = counting
    try:
        first = filesystem.snapshot(root)
        for _ in range(5):
            filesystem.snapshot(root)
        assert reads['count'] == 1, 'polling repetido não pode reler o disco'
        assert first[0]['status'] == 'completed'

        # A new run changes the fingerprint, so the next call rebuilds.
        (root / 'campaigns' / 'runs' / ('run-' + 'b' * 32)).mkdir()
        filesystem.snapshot(root)
        assert reads['count'] == 2
    finally:
        filesystem.media_catalog = original


def test_the_active_run_is_labelled_without_rebuilding(root):
    """active_id only decides a label, so it must not invalidate the cache."""
    from studio_ai.infrastructure.persistence import filesystem

    run_id = 'run-' + 'c' * 32
    directory = root / 'campaigns' / 'runs' / run_id
    directory.mkdir(parents=True)
    (directory / 'events.jsonl').write_text('{"event": "run_started"}\n', encoding='utf-8')

    filesystem.snapshot(root)
    labelled = filesystem.snapshot(root, active_id=run_id)
    assert labelled[0]['status'] == 'running'
    assert filesystem.snapshot(root)[0]['status'] == 'interrupted'
