from concurrent.futures import ThreadPoolExecutor
import threading

from realcenter_marketing.bootstrap import registry as module


def test_concurrent_first_requests_do_not_close_shared_scheduler(tmp_path, monkeypatch):
    registry = module.TenantRegistry(tmp_path)
    original = module.CampaignService
    barrier = threading.Barrier(2)

    def build(*args, **kwargs):
        service = original(*args, **kwargs)
        barrier.wait(timeout=5)
        return service

    monkeypatch.setattr(module, 'CampaignService', build)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(registry.context, 'store') for _ in range(2)]
            contexts = [future.result(timeout=10) for future in futures]
        assert contexts[0] is contexts[1]
        scheduler = contexts[0].service.scheduler
        assert scheduler.acquire(), 'An idle store must accept work after concurrent initialization'
        scheduler.release()
    finally:
        registry.close(timeout=1)


def test_evicted_store_can_accept_work_when_reopened(tmp_path):
    registry = module.TenantRegistry(tmp_path, max_hot=1)
    try:
        registry.context('first')
        registry.context('second')
        context = registry.context('first')
        assert context.service.scheduler.acquire()
        context.service.scheduler.release()
    finally:
        registry.close(timeout=1)


def test_briefing_without_active_run_is_not_evicted(tmp_path):
    registry = module.TenantRegistry(tmp_path, max_hot=1)
    first = registry.context('first')
    assert first.service.scheduler.acquire()
    try:
        registry.context('second')
        assert registry.context('first') is first
        assert first.service.busy
    finally:
        first.service.scheduler.release()
        registry.close(timeout=1)
