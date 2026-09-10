"""One local execution at a time, with an explicit shutdown lifecycle."""
import threading


class LocalExecutionScheduler:
    def __init__(self):
        self.lock = threading.Lock()
        self._guard = threading.Lock()
        self._closing = False
        self._thread = None

    def acquire(self):
        with self._guard:
            return not self._closing and self.lock.acquire(blocking=False)

    def release(self):
        self.lock.release()

    def submit(self, work):
        # The caller owns the execution lock until work releases it. Shutdown
        # waits for that lock even if submission and close race with each other.
        self._thread = threading.Thread(target=work, name='campaign-execution', daemon=False)
        self._thread.start()

    def close(self, timeout=None):
        with self._guard:
            self._closing = True
        acquired = self.lock.acquire() if timeout is None else self.lock.acquire(timeout=timeout)
        if acquired:
            self.lock.release()
        return acquired
