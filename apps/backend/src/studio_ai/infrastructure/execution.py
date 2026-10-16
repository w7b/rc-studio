"""Bounded execution: one run per tenant for fairness, a global ceiling for capacity.

A tenant holding its own slot is what keeps one store from stacking two runs, and the
worker ceiling is what keeps ten stores from starting ten paid runs at once. The two
limits are independent on purpose: the slot protects the user's expectations, the
ceiling protects the machine and the bill.
"""
import queue
import threading
from concurrent.futures import Future


class WaitingWork:
    """A synchronous caller owns its slot and needs notification if work is dropped."""
    def __init__(self, work):
        self.work, self.future = work, Future()

    def __call__(self):
        try:
            self.future.set_result(self.work())
        except BaseException as exc:
            self.future.set_exception(exc)

    def cancel(self):
        self.future.cancel()


class TenantScheduler:
    """One execution slot for a single tenant. Satisfies the ExecutionScheduler port."""

    def __init__(self, pool, key, owns_pool=False):
        self._pool, self.key, self._owns_pool = pool, key, owns_pool
        self.lock = threading.Lock()
        self._guard = threading.Lock()
        self._closing = False

    def acquire(self):
        with self._guard:
            if self._closing or self._pool.closing:
                return False
            return self.lock.acquire(blocking=False)

    def release(self):
        self.lock.release()

    def submit(self, work):
        # The caller owns this tenant's slot until work releases it. The slot stays held
        # while the run waits in line, so queueing can never let a tenant stack two runs.
        self._pool.enqueue(self.key, work)

    def call(self, work):
        waiting = WaitingWork(work)
        self.submit(waiting)
        return waiting.future.result()

    def close_slot(self, timeout=None):
        """Drain this tenant only. Shutdown waits for the running work even if a
        submission races with close."""
        with self._guard:
            self._closing = True
        acquired = self.lock.acquire() if timeout is None else self.lock.acquire(timeout=timeout)
        if acquired:
            self.lock.release()
        return acquired

    def close(self, timeout=None):
        # A scheduler that owns its pool tears the workers down too, so a standalone
        # data root keeps the single-execution lifecycle it has always had.
        if self._owns_pool:
            return self._pool.close(timeout)
        return self.close_slot(timeout)

    def position(self):
        return self._pool.position(self.key)


class ExecutionPool:
    """A fixed set of workers draining one FIFO queue shared by every tenant."""

    def __init__(self, capacity=2):
        self.capacity = max(1, capacity)
        self.closing = False
        self._queue = queue.Queue()
        self._schedulers = {}
        self._pending = []
        self._workers = []
        self._guard = threading.Lock()

    def scheduler(self, key, owns_pool=False):
        with self._guard:
            if key not in self._schedulers:
                self._schedulers[key] = TenantScheduler(self, key, owns_pool)
            return self._schedulers[key]

    def enqueue(self, key, work):
        with self._guard:
            if self.closing:
                if isinstance(work, WaitingWork):
                    work.cancel()
                else:
                    self._discard(key)
                return
            self._pending.append(key)
            while len(self._workers) < self.capacity:
                # Daemon threads: a worker idle on an empty queue holds nothing, and a
                # non-daemon one would keep the interpreter alive forever. The promise
                # that running work finishes lives in close(), which waits on the
                # tenant locks before the process goes down.
                worker = threading.Thread(target=self._drain, name=f'campaign-execution-{len(self._workers)}', daemon=True)
                self._workers.append(worker)
                worker.start()
            # Ordered with the closing flag: no accepted work can land behind the
            # shutdown sentinels after all workers have already exited.
            self._queue.put((key, work))

    def position(self, key):
        """Place in line, 1-based. None once the work is running or finished."""
        with self._guard:
            return self._pending.index(key) + 1 if key in self._pending else None

    def running(self):
        with self._guard:
            return [key for key, scheduler in self._schedulers.items()
                    if scheduler.lock.locked() and key not in self._pending]

    def _discard(self, key):
        """Hand back the slot a queued run was holding. It never started, so nothing was
        spent; its directory keeps only run_started and snapshot() reports it as
        interrupted, which retry already knows how to resume."""
        slot = self._schedulers.get(key)
        if slot is not None and slot.lock.locked():
            try:
                slot.release()
            except RuntimeError:
                pass

    def _drain(self):
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                key, work = item
                with self._guard:
                    if key in self._pending:
                        self._pending.remove(key)
                    closing = self.closing
                if closing:
                    if isinstance(work, WaitingWork):
                        # Its waiting caller refunds unused quota and releases the
                        # tenant lock. Do not release the same slot a second time.
                        work.cancel()
                    else:
                        self._discard(key)
                    continue
                work()
            finally:
                self._queue.task_done()

    def close(self, timeout=None):
        """Wait for work already running; discard what never started. A queued run has
        spent nothing and its directory holds only run_started, which snapshot() already
        reports as interrupted — and retry picks it up from there."""
        with self._guard:
            self.closing = True
            schedulers, workers = list(self._schedulers.values()), list(self._workers)
        # The queue is not emptied here. Whatever a worker has already taken must still
        # finish, and whatever is still waiting is dropped by the worker itself once it
        # sees the pool closing — which is what keeps close() from ever waiting on a run
        # that has not started.
        drained = all(scheduler.close_slot(timeout) for scheduler in schedulers) if schedulers else True
        for _ in workers:
            self._queue.put(None)
        for worker in workers:
            worker.join(timeout)
        return drained


def LocalExecutionScheduler():
    """One execution at a time for a standalone data root, owning its own pool."""
    return ExecutionPool(capacity=1).scheduler('local', owns_pool=True)
