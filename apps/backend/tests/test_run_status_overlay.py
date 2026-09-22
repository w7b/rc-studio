from queue_fake import FakeJobQueue
from realcenter_marketing.application.commands import RunRequest
from realcenter_marketing.bootstrap.registry import TenantRegistry
from realcenter_marketing.infrastructure.persistence.filesystem import _SNAPSHOT_CACHE


def test_queue_overlay_never_enters_snapshot_cache(root):
    queue = FakeJobQueue()
    registry = TenantRegistry(root.parent, queue_for=lambda *args: queue)
    try:
        context = registry.context('store', str(root), tenant_id=1)
        run_id = context.service.start(RunRequest(request='Teste de fila', mode='demo'))
        state = context.run_state()
        assert state['busy'] and state['active_id'] == run_id
        assert state['runs'][0]['status'] == 'queued'
        assert _SNAPSHOT_CACHE[str(root)][1][0]['status'] == 'interrupted'
        queue.jobs[0]['status'] = 'running'
        assert context.run_state()['runs'][0]['status'] == 'running'
        assert _SNAPSHOT_CACHE[str(root)][1][0]['status'] == 'interrupted'
        context.service.resume('campaign', run_id, queue.jobs[0]['payload'])
        queue.jobs[0]['status'] = 'done'
        state = context.run_state()
        assert state['runs'][0]['status'] == 'completed'
        assert not state['busy'] and state['active_id'] is None
        context.service.scheduler.acquire()
        try:
            assert context.run_state()['busy']
        finally:
            context.service.scheduler.release()
    finally:
        registry.close()


def test_context_rebinds_after_session_or_root_change(tmp_path):
    queue = FakeJobQueue()
    registry = TenantRegistry(tmp_path, queue_for=lambda *args: queue,
                              quota_for=lambda tenant_id, role: (tenant_id, role))
    try:
        assert registry.context('store').service.queue is None
        signed_in = registry.context('store', tenant_id=7, role='DEFAULT')
        assert signed_in.service.queue is queue
        paid = registry.context('store', tenant_id=7, role='PAID')
        assert paid.service.quota == (7, 'PAID')
        moved = registry.context('store', str(tmp_path / 'moved'), tenant_id=7, role='PAID')
        assert moved.root == (tmp_path / 'moved').resolve()
        assert moved.service.scheduler is signed_in.service.scheduler
    finally:
        registry.close()
