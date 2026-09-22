from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from realcenter_marketing.application.consultations import ConsultationService
from realcenter_marketing.domain.consultations import ConsultationRequest
from realcenter_marketing.infrastructure.execution import ExecutionPool
from realcenter_marketing.infrastructure.persistence.campaign_repository import FileCampaignRepository
from test_consultations import media_plan
from test_quota import quota


@pytest.mark.parametrize('shutdown', [False, True])
def test_consultations_share_global_capacity_and_refund_discarded_work(tmp_path, shutdown):
    pool = ExecutionPool(capacity=1)
    hold, first_started, second_started, submitted = (threading.Event() for _ in range(4))
    allowance = quota()

    def service(key, entered, quota=None):
        async def execute(*args):
            entered.set()
            assert hold.wait(5)
            return media_plan()
        scheduler = pool.scheduler(key)
        if key == 'second':
            original = scheduler.acquire
            def acquire():
                result = original()
                submitted.set()
                return result
            scheduler.acquire = acquire
        return ConsultationService(FileCampaignRepository(tmp_path / key), scheduler, execute,
                                   lambda request: None, quota)

    first, second = service('first', first_started), service('second', second_started, allowance)
    request = ConsultationRequest(role='performance', request='Planeje')
    with ThreadPoolExecutor(max_workers=2) as callers:
        a = callers.submit(first.run, request)
        b = None
        try:
            assert first_started.wait(3)
            b = callers.submit(second.run, request)
            assert submitted.wait(3)
            assert not second_started.wait(.15), 'second provider bypassed the global capacity'
            if shutdown:
                pool.close(timeout=.01)
            hold.set()
            assert a.result(3)['role'] == 'performance'
            if shutdown:
                with pytest.raises(ValueError, match='Não foi possível'):
                    b.result(3)
                assert not second_started.is_set()
                assert allowance.summary()['metrics']['assists']['used'] == 0
            else:
                assert b.result(3)['role'] == 'performance'
                assert second_started.is_set()
                assert allowance.summary()['metrics']['assists']['used'] == 1
            assert not first.scheduler.lock.locked()
            assert not second.scheduler.lock.locked()
        finally:
            hold.set()
            pool.close(timeout=3)


def test_shutdown_between_acquire_and_enqueue_returns_instead_of_hanging(tmp_path):
    pool = ExecutionPool(capacity=1)
    warm = pool.scheduler('warm')
    finished = threading.Event()
    assert warm.acquire()
    warm.submit(lambda: (warm.release(), finished.set()))
    assert finished.wait(3)
    scheduler = pool.scheduler('late')
    allowance = quota()
    repository = FileCampaignRepository(tmp_path)
    create = repository.create_consultation

    def close_during_setup():
        pool.close(timeout=.05)
        return create()

    repository.create_consultation = close_during_setup
    async def forbidden(*args):
        pytest.fail('provider must not start after shutdown')
    service = ConsultationService(repository, scheduler, forbidden, lambda _: None, allowance)
    done, errors = threading.Event(), []

    def caller():
        try:
            service.run(ConsultationRequest(role='performance', request='Planeje'))
        except Exception as exc:
            errors.append(exc)
        finally:
            done.set()

    thread = threading.Thread(target=caller, daemon=True)
    thread.start()
    assert done.wait(3), 'synchronous caller stranded behind shutdown sentinels'
    thread.join(1)
    assert len(errors) == 1 and isinstance(errors[0], ValueError)
    assert allowance.summary()['metrics']['assists']['used'] == 0
    assert not scheduler.lock.locked()
