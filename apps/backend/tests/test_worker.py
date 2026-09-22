import os
import threading
from types import SimpleNamespace

import pytest

from queue_fake import FakeJobQueue
from script_loader import load_script
from realcenter_marketing.application.commands import RunRequest
from realcenter_marketing.bootstrap.registry import TenantRegistry

worker = load_script('worker')


class WorkerQueue:
    def __init__(self, job):
        self.job = job
        self.worker = 'test-worker'
        self.status, self.error = 'queued', None
        self.pulsed = threading.Event()

    def claim(self):
        if self.status != 'queued':
            return None
        self.status = 'running'
        return {**self.job, 'claimed_by': self.worker}

    def heartbeat(self, job_id, worker=None):
        assert worker == self.worker
        self.pulsed.set()
        return True

    def finish(self, job_id, error=None, worker=None):
        assert worker == self.worker
        self.status, self.error = ('failed' if error else 'done'), error

    def requeue(self, job_id, worker=None):
        assert worker == self.worker
        self.status = 'queued'

    def pending(self):
        return int(self.status in ('queued', 'running'))


@pytest.fixture
def execution(root):
    pending = FakeJobQueue()
    web = TenantRegistry(root.parent, queue_for=lambda *args: pending)
    background = TenantRegistry(root.parent, quota_for=None, queue_for=None)
    context = web.context('store', str(root), tenant_id=1)
    run_id = context.service.start(RunRequest(request='Teste worker', mode='demo'))
    queue = WorkerQueue({**pending.jobs[0], 'tenant_slug': 'store', 'tenant_id': 1, 'root_path': str(root)})
    try:
        yield background, queue, run_id
    finally:
        web.close()
        background.close()


def test_worker_waits_for_completion_and_heartbeats_during_execution(execution, monkeypatch):
    registry, queue, run_id = execution
    context = registry.context('store', queue.job['root_path'], tenant_id=1, role='OWNER')
    original = context.service.execute
    async def execute(*args):
        assert queue.status == 'running'
        assert queue.pulsed.wait(2)
        return await original(*args)
    context.service.execute = execute
    monkeypatch.setattr(worker, 'HEARTBEAT_SECONDS', 0.01)
    assert worker.run_once(registry, queue)
    assert queue.status == 'done'
    assert context.service.repository.last_event(run_id) == 'run_completed'
    assert not worker.run_once(registry, queue)


def test_worker_records_real_failure_without_refund(execution):
    registry, queue, run_id = execution
    context = registry.context('store', queue.job['root_path'], tenant_id=1, role='OWNER')
    async def fail(*args):
        raise RuntimeError('provider failed')
    context.service.execute = fail
    assert context.service.quota is None and context.service.queue is None
    worker.run_once(registry, queue)
    assert queue.status == 'failed' and 'provider failed' in queue.error
    assert context.service.repository.last_event(run_id) == 'run_failed'


def test_busy_worker_requeues(execution):
    registry, queue, _ = execution
    context = registry.context('store', queue.job['root_path'], tenant_id=1, role='OWNER')
    context.service.scheduler.acquire()
    try:
        worker.run_once(registry, queue)
        assert queue.status == 'queued'
    finally:
        context.service.scheduler.release()


def test_missing_mount_is_terminal(execution, tmp_path):
    registry, queue, _ = execution
    queue.job['root_path'] = str(tmp_path / 'missing-mount')
    worker.run_once(registry, queue)
    assert queue.status == 'failed'
    assert 'diretório' in queue.error and 'montagem' in queue.error
    assert not worker.run_once(registry, queue)


def test_healthcheck_requires_fresh_local_heartbeat(tmp_path, monkeypatch):
    path = tmp_path / 'heartbeat'
    queue = WorkerQueue({})
    now = 1_700_000_000.0
    monkeypatch.setattr(worker.time, 'time', lambda: now)
    with pytest.raises(FileNotFoundError):
        worker.healthcheck(queue, path)
    path.touch()
    os.utime(path, (now, now))
    worker.healthcheck(queue, path)
    fresh = now - worker.LEASE_SECONDS + 1
    os.utime(path, (fresh, fresh))
    worker.healthcheck(queue, path)
    expired = now - worker.LEASE_SECONDS
    os.utime(path, (expired, expired))
    with pytest.raises(RuntimeError, match='expirado'):
        worker.healthcheck(queue, path)


@pytest.mark.parametrize('ahead, healthy', [(0.01, True), (2, True), (3, True), (3.01, False)])
def test_healthcheck_tolerates_filesystem_clock_rounding(tmp_path, monkeypatch, ahead, healthy):
    path = tmp_path / 'heartbeat'
    path.touch()
    now = 1_700_000_000.0
    os.utime(path, (now + ahead, now + ahead))
    monkeypatch.setattr(worker.time, 'time', lambda: now)
    if healthy:
        worker.healthcheck(WorkerQueue({}), path)
    else:
        with pytest.raises(RuntimeError, match='expirado'):
            worker.healthcheck(WorkerQueue({}), path)


def test_shutdown_finishes_current_job_before_closing_registry(execution, tmp_path, monkeypatch):
    registry, queue, run_id = execution
    context = registry.context('store', queue.job['root_path'], tenant_id=1, role='OWNER')
    original_execute, original_close = context.service.execute, registry.close
    closed = []
    async def execute(*args):
        worker.stop()
        assert queue.status == 'running' and not closed
        return await original_execute(*args)
    def close(timeout=None):
        assert queue.status == 'done'
        assert context.service.repository.last_event(run_id) == 'run_completed'
        closed.append(timeout)
        return original_close(timeout)
    context.service.execute = execute
    monkeypatch.setattr(registry, 'close', close)
    identity_closed = []
    identity = SimpleNamespace(database=object(), close=lambda: identity_closed.append(True))
    monkeypatch.setattr(worker, 'build_identity', lambda: identity)
    monkeypatch.setattr(worker, 'PostgresJobQueue', lambda _: queue)
    monkeypatch.setattr(queue, 'requeue_stale', lambda: 0, raising=False)
    monkeypatch.setattr(queue, 'abandon_exhausted', lambda: 0, raising=False)
    monkeypatch.setattr(worker, 'TenantRegistry', lambda *args, **kwargs: registry)
    monkeypatch.setattr(worker.signal, 'signal', lambda *args: None)
    monkeypatch.setattr(worker, 'running', True)
    heartbeat = tmp_path / 'worker-health'
    monkeypatch.setenv('WORKER_HEARTBEAT_FILE', str(heartbeat))
    worker.main([])
    assert closed == [worker.DRAIN_SECONDS]
    assert identity_closed == [True]
    assert not heartbeat.exists()
