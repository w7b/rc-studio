import threading

import pytest

from realcenter_marketing.infrastructure.execution import LocalExecutionScheduler
from realcenter_marketing.infrastructure.process_lease import ProcessLease
from realcenter_marketing.bootstrap.services import CampaignService
from realcenter_marketing.application.commands import ImageRequest
from realcenter_marketing.application.errors import BusyError


def test_close_waits_for_work_and_rejects_new_submissions():
    scheduler = LocalExecutionScheduler()
    gate = threading.Event()
    assert scheduler.acquire()
    def work():
        gate.wait(3)
        scheduler.release()
    scheduler.submit(work)
    try:
        assert not scheduler.close(timeout=.01)
        assert not scheduler.acquire()
    finally:
        gate.set()
        assert scheduler.close(timeout=3)
    assert not scheduler.acquire()


def test_only_one_process_lease_per_data_root_and_release(tmp_path):
    first = ProcessLease(tmp_path).acquire()
    try:
        with pytest.raises(RuntimeError, match='processo'):
            ProcessLease(tmp_path).acquire()
        # Independent data roots may run in parallel.
        other = ProcessLease(tmp_path / 'other').acquire()
        other.close()
    finally:
        first.close()
    again = ProcessLease(tmp_path).acquire()
    again.close()


def test_failed_image_setup_releases_execution_slot(settings, demo, root, tmp_path, monkeypatch):
    import asyncio
    from realcenter_marketing.bootstrap.campaigns import create_campaign
    from realcenter_marketing.domain.campaigns import CampaignBrief
    from realcenter_marketing.infrastructure.observability.journal import RunJournal
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Teste'), settings, model=demo))
    campaign.execution_mode = 'live'
    run_id = 'run-' + 'e' * 32
    journal = RunJournal(root / 'campaigns/runs' / run_id)
    journal.save('campaign', campaign)
    service = CampaignService(root)
    monkeypatch.setattr(service, 'validate_live', lambda *_: None)
    def unavailable(*args):
        raise OSError('unavailable')
    monkeypatch.setattr(service.repository, 'resume', unavailable)
    with pytest.raises(OSError):
        service.image(run_id, ImageRequest())
    assert service.active_id is None
    assert service.lock.acquire(blocking=False)
    service.lock.release()


def test_closed_service_cannot_start_more_work(root):
    from realcenter_marketing.application.commands import RunRequest
    service = CampaignService(root)
    assert service.close(timeout=0)
    with pytest.raises(BusyError):
        service.start(RunRequest(request='Teste', mode='demo'))
