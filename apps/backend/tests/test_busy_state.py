import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from realcenter_marketing.application.commands import AssistRequest, RunRequest
from realcenter_marketing.application.errors import BusyError
from realcenter_marketing.application.identity.quota import QuotaError, UsageQuota, limits_for
from realcenter_marketing.bootstrap.services import CampaignService
from realcenter_marketing.infrastructure.identity.memory_quotas import MemoryQuotaLedger


@pytest.mark.parametrize('operation', ['assist', 'campaign', 'image'])
def test_busy_rejection_does_not_consume_quota(tmp_path, operation):
    ledger = MemoryQuotaLedger()
    service = CampaignService(tmp_path, quota=UsageQuota(ledger, 1, 'DEFAULT', lambda: '2026-09'))
    service.validate_live = lambda *args: None
    service.lock.acquire()
    try:
        with pytest.raises(BusyError):
            if operation == 'assist':
                service.assist(AssistRequest(request='Ideia'))
            elif operation == 'campaign':
                service.start(RunRequest(request='Ideia'))
            else:
                service.repository.campaign = lambda _: SimpleNamespace(execution_mode='live')
                service.image('run-example')
        assert not any(ledger.used(1, '2026-09').values())
    finally:
        service.lock.release()
        service.close()


def test_http_reports_briefing_busy_until_provider_finishes(isolated_root, monkeypatch):
    from realcenter_marketing.presentation.http.server import make_server
    entered, release = threading.Event(), threading.Event()
    async def improve(*args, **kwargs):
        entered.set()
        release.wait(10)
        raise RuntimeError('provider failed')
    monkeypatch.setattr('realcenter_marketing.bootstrap.settings.Settings.validate_live', lambda self: None)
    monkeypatch.setattr('realcenter_marketing.bootstrap.services.improve_brief', improve)
    server = make_server(isolated_root, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    def get(path):
        with urlopen(base + path) as response:
            return json.load(response)
    pool = ThreadPoolExecutor(1)
    try:
        token = get('/api/config')['token']
        request = Request(base + '/api/brief-assist', data=json.dumps({'request': 'Ideia'}).encode(),
                          headers={'Content-Type': 'application/json', 'X-App-Token': token})
        future = pool.submit(urlopen, request)
        assert entered.wait(5)
        state = get('/api/runs')
        assert state['active_id'] is None
        assert state['busy'] is True
        release.set()
        with pytest.raises(HTTPError):
            future.result(5)
        assert get('/api/runs')['busy'] is False
    finally:
        release.set()
        pool.shutdown()
        server.shutdown()
        server.server_close()
        thread.join(2)


@pytest.mark.parametrize('operation,metric', [('assist', 'assists'), ('campaign', 'campaigns')])
def test_quota_rejection_releases_execution_slot(tmp_path, operation, metric):
    allowance = UsageQuota(MemoryQuotaLedger(), 1, 'DEFAULT', lambda: '2026-09')
    allowance.reserve(**{metric: limits_for('DEFAULT')[metric]})
    service = CampaignService(tmp_path, quota=allowance)
    service.validate_live = lambda *args: None
    try:
        with pytest.raises(QuotaError):
            if operation == 'assist':
                service.assist(AssistRequest(request='Ideia'))
            else:
                service.start(RunRequest(request='Ideia'))
        assert service.busy is False
    finally:
        service.close()
