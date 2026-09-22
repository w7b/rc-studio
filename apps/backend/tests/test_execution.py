import threading

import pytest

from realcenter_marketing.infrastructure.execution import LocalExecutionScheduler
from realcenter_marketing.infrastructure.process_lease import ProcessLease
from realcenter_marketing.bootstrap.services import CampaignService
from realcenter_marketing.application.commands import ImageRequest
from realcenter_marketing.application.errors import BusyError


def test_close_waits_for_work_and_rejects_new_submissions():
    scheduler = LocalExecutionScheduler()
    started, gate = threading.Event(), threading.Event()
    assert scheduler.acquire()
    def work():
        started.set()
        gate.wait(3)
        scheduler.release()
    scheduler.submit(work)
    # Submitting now means "queued"; close only owes a wait to work already in flight.
    assert started.wait(3)
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


def test_each_tenant_owns_its_slot_so_one_store_cannot_stack_two_runs():
    from realcenter_marketing.infrastructure.execution import ExecutionPool
    pool = ExecutionPool(capacity=2)
    loja_a, loja_b = pool.scheduler('loja-a'), pool.scheduler('loja-b')
    try:
        assert loja_a.acquire()
        # The same store asking twice is the case that must keep answering BusyError.
        assert not loja_a.acquire()
        # A different store is unaffected by its neighbour.
        assert loja_b.acquire()
    finally:
        loja_a.release()
        loja_b.release()
        pool.close(timeout=3)


def test_work_beyond_capacity_waits_in_line_with_a_visible_position():
    from realcenter_marketing.infrastructure.execution import ExecutionPool
    pool = ExecutionPool(capacity=1)
    loja_a, loja_b = pool.scheduler('loja-a'), pool.scheduler('loja-b')
    started, hold, ran_b = threading.Event(), threading.Event(), threading.Event()
    try:
        assert loja_a.acquire()
        def first():
            started.set()
            hold.wait(3)
            loja_a.release()
        loja_a.submit(first)
        assert started.wait(3)

        assert loja_b.acquire()
        def second():
            ran_b.set()
            loja_b.release()
        loja_b.submit(second)

        # The only worker is busy with loja-a, so loja-b is queued, not rejected.
        assert loja_b.position() == 1
        assert not ran_b.wait(.2)

        hold.set()
        assert ran_b.wait(3)
        assert loja_b.position() is None
    finally:
        hold.set()
        pool.close(timeout=3)


def test_close_discards_work_that_never_started():
    """A queued run has spent nothing, so shutdown drops it and hands its slot back
    instead of blocking on a queue that could outlast the stop grace period."""
    from realcenter_marketing.infrastructure.execution import ExecutionPool
    pool = ExecutionPool(capacity=1)
    loja_a, loja_b = pool.scheduler('loja-a'), pool.scheduler('loja-b')
    started, hold, ran_b = threading.Event(), threading.Event(), threading.Event()
    outcome = []
    try:
        assert loja_a.acquire()
        def first():
            started.set()
            hold.wait(5)
            loja_a.release()
        loja_a.submit(first)
        assert started.wait(3)

        # loja-b is queued behind the only worker, which is still inside first().
        assert loja_b.acquire()
        loja_b.submit(lambda: (ran_b.set(), loja_b.release()))
        assert loja_b.position() == 1

        closer = threading.Thread(target=lambda: outcome.append(pool.close(timeout=5)))
        closer.start()
        hold.set()
        closer.join(8)

        assert outcome == [True]
        assert not ran_b.is_set()
        # The discarded run gave its slot back rather than leaving the store locked out.
        assert not loja_b.lock.locked()
        assert not pool.scheduler('loja-c').acquire()
    finally:
        hold.set()
