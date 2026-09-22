import base64

import pytest

from queue_fake import FakeJobQueue
from realcenter_marketing.application.commands import RunRequest
from realcenter_marketing.application.errors import BusyError
from realcenter_marketing.bootstrap.services import CampaignService


def test_admission_enqueues_without_execution_and_resume_finishes(root):
    service = CampaignService(root)
    service.queue = queue = FakeJobQueue()
    request = RunRequest(request='Campanha de teste', mode='demo',
                         upload=base64.b64encode((root / 'brand/references/fixture.png').read_bytes()).decode(),
                         reference_upload=base64.b64encode((root / 'brand/references/fixture.png').read_bytes()).decode())
    try:
        run_id = service.start(request)
        assert len(queue.jobs) == 1
        job = queue.jobs[0]
        assert job['payload']['request']['upload'] is None
        assert job['payload']['request']['reference_upload'] is None
        assert service.repository.last_event(run_id) == 'run_queued'
        assert not service.repository.has_campaign(run_id)
        assert not service.busy
        with pytest.raises(BusyError):
            service.retry(run_id)
        service.queue = None
        service.resume(job['kind'], run_id, job['payload'])
        assert service.repository.last_event(run_id) == 'run_completed'
        assert service.repository.has_campaign(run_id)
    finally:
        service.close()


def test_resume_propagates_real_execution_failure(root):
    service = CampaignService(root)
    service.queue = queue = FakeJobQueue()
    async def fail(*args):
        raise RuntimeError('provider exploded')
    try:
        run_id = service.start(RunRequest(request='Campanha de teste', mode='demo'))
        service.execute = fail
        service.queue = None
        with pytest.raises(RuntimeError, match='provider exploded'):
            service.resume('campaign', run_id, queue.jobs[0]['payload'])
        assert service.repository.last_event(run_id) == 'run_failed'
        assert not service.busy
    finally:
        service.close()


def test_missing_run_reports_mount_problem_without_creating_directory(root):
    service = CampaignService(root)
    try:
        with pytest.raises(ValueError, match='diretório.*montagem'):
            service.resume('campaign', 'run-' + 'a' * 32,
                           {'request': {'request': 'teste', 'mode': 'demo'}})
        assert not service.busy
    finally:
        service.close()


def test_worker_may_complete_before_enqueue_returns(root):
    web, background = CampaignService(root), CampaignService(root)
    class ImmediateQueue(FakeJobQueue):
        def enqueue(self, kind, payload, run_id):
            result = super().enqueue(kind, payload, run_id)
            background.resume(kind, run_id, payload)
            self.jobs[-1]['status'] = 'done'
            return result
    web.queue = ImmediateQueue()
    try:
        run_id = web.start(RunRequest(request='Teste rápido', mode='demo'))
        assert web.repository.last_event(run_id) == 'run_completed'
        assert not web.busy
    finally:
        web.close()
        background.close()


def test_enqueue_failure_refunds_only_web_reservation_and_releases_slot(root):
    from realcenter_marketing.application.identity.quota import UsageQuota
    from realcenter_marketing.infrastructure.identity.memory_quotas import MemoryQuotaLedger
    ledger = MemoryQuotaLedger()
    service = CampaignService(root, quota=UsageQuota(ledger, 1, 'DEFAULT', lambda: '2026-09'))
    service.validate_live = lambda *args: None
    class UnavailableQueue(FakeJobQueue):
        def enqueue(self, *args):
            raise OSError('database unavailable')
    service.queue = UnavailableQueue()
    try:
        with pytest.raises(OSError, match='database unavailable'):
            service.start(RunRequest(request='Campanha live'))
        assert not service.busy
        assert ledger.used(1, '2026-09').get('campaigns', 0) == 0
        run_id = next((root / 'campaigns/runs').iterdir()).name
        assert service.repository.last_event(run_id) == 'run_failed'
    finally:
        service.close()


def test_worker_failure_keeps_reservation_as_an_audit_record(root):
    from realcenter_marketing.application.identity.quota import UsageQuota
    from realcenter_marketing.infrastructure.identity.memory_quotas import MemoryQuotaLedger
    ledger = MemoryQuotaLedger()
    web = CampaignService(root, quota=UsageQuota(ledger, 1, 'DEFAULT', lambda: '2026-09'))
    worker = CampaignService(root)
    web.queue = queue = FakeJobQueue()
    web.validate_live = lambda *args: None
    async def fail(*args):
        raise RuntimeError('provider failure')
    worker.execute = fail
    try:
        run_id = web.start(RunRequest(request='Campanha live'))
        payload = queue.jobs[0]['payload']
        assert payload['reservation'] == {'tenant_id': 1, 'period': '2026-09', 'amounts': {'campaigns': 1}}
        with pytest.raises(RuntimeError):
            worker.resume('campaign', run_id, payload)
        assert ledger.used(1, '2026-09')['campaigns'] == 1
    finally:
        web.close()
        worker.close()


def test_image_revision_materializes_inputs_before_enqueue_and_rehydrates(root):
    from realcenter_marketing.application.commands import ImageRequest
    from realcenter_marketing.infrastructure.persistence.filesystem import media_catalog
    web, worker = CampaignService(root), CampaignService(root)
    try:
        admission = web.admit(RunRequest(request='Base da revisão', mode='demo'))
        web.run(admission)
        run_id = admission.run_id
        campaign = web.repository.campaign(run_id).model_copy(update={'execution_mode': 'live'})
        admission.journal.save('campaign', campaign)
        picture = (root / 'brand/references/fixture.png').read_bytes()
        image_path = admission.journal.directory / 'feed-original.png'
        image_path.write_bytes(picture)
        image_id = next(key for key, value in media_catalog(root).items() if value['path'] == image_path)
        web.queue = queue = FakeJobQueue()
        web.validate_live = lambda *args: None
        request = ImageRequest(changes='Mais contraste', base_image_id=image_id,
                               reference_upload=base64.b64encode(picture).decode())
        assert web.image(run_id, request) == run_id
        payload = queue.jobs[0]['payload']
        assert payload['request']['reference_upload'] is None
        assert payload['base_image'] == 'feed-original.png'
        assert payload['revision_reference'].startswith('revision-inputs/')
        revision = admission.journal.directory / payload['revision_reference']
        assert revision.read_bytes() == picture
        calls = []
        def generate(campaign, journal, product, changes, base, reference, **kwargs):
            calls.append((changes, base.read_bytes(), reference.read_bytes()))
        worker.images.execute = generate
        worker.resume('image', run_id, payload)
        assert calls == [('Mais contraste', picture, picture)]
        assert web.repository.last_event(run_id) == 'run_completed'
    finally:
        web.close()
        worker.close()
