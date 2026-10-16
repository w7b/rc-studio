"""Fixed-window attempt counters.

In-process by default, which is correct while the studio is a single process. The
Postgres-backed variant exists so the count survives a restart, because an attacker who
can crash or wait out a process should not get a fresh budget.
"""
import threading
import time


class MemoryRateLimiter:
    def __init__(self):
        self._windows = {}
        self._guard = threading.Lock()

    def hit(self, key, limit, window_seconds):
        stamp = time.monotonic()
        with self._guard:
            start, count = self._windows.get(key, (stamp, 0))
            if stamp - start >= window_seconds:
                start, count = stamp, 0
            count += 1
            self._windows[key] = (start, count)
            return count <= limit

    def reset(self, key):
        with self._guard:
            self._windows.pop(key, None)
