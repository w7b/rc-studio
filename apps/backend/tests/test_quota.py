"""Monthly allowances.

The test that matters most is that a refused run writes nothing: the reservation has to
happen before uploads are saved and before any provider is called, because a call that
already happened cannot be un-billed.
"""
import json
import threading
from http.cookies import SimpleCookie
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from identity_fake import FakeIdentityStore
from realcenter_marketing.application.identity.quota import PLANS, QuotaError, UsageQuota, limits_for
from realcenter_marketing.application.identity.service import IdentityService
from realcenter_marketing.bootstrap.platform import Identity
from realcenter_marketing.infrastructure.identity.memory_quotas import MemoryQuotaLedger
from realcenter_marketing.infrastructure.identity.rate_limit import MemoryRateLimiter
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


# -- through HTTP -------------------------------------------------------------

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
    from realcenter_marketing.infrastructure.identity.quotas import current_period
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
    from realcenter_marketing.infrastructure.identity.quotas import current_period
    assert ledger.used(loja.id, current_period()).get('campaigns', 0) == 0
