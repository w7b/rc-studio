"""In-process quota counters for the standalone deployment and the offline suite.

Correct for one process, which is exactly what standalone is. A shared deployment uses the
Postgres ledger, because there the counter has to survive a restart and be safe against
two requests arriving at once.
"""
import threading


class MemoryQuotaLedger:
    def __init__(self):
        self._counters = {}
        self._guard = threading.Lock()

    def reserve(self, tenant_id, period, amounts, limits):
        with self._guard:
            bucket = self._counters.setdefault((tenant_id, period), {})
            for metric, count in amounts.items():
                limit = limits.get(metric)
                if limit is not None and bucket.get(metric, 0) + count > limit:
                    return (metric, bucket.get(metric, 0), limit)
            for metric, count in amounts.items():
                bucket[metric] = bucket.get(metric, 0) + count
            return True

    def record(self, tenant_id, period, amounts):
        with self._guard:
            bucket = self._counters.setdefault((tenant_id, period), {})
            for metric, count in amounts.items():
                bucket[metric] = bucket.get(metric, 0) + count

    def release(self, tenant_id, period, amounts):
        with self._guard:
            bucket = self._counters.setdefault((tenant_id, period), {})
            for metric, count in amounts.items():
                bucket[metric] = max(bucket.get(metric, 0) - count, 0)

    def used(self, tenant_id, period):
        with self._guard:
            return dict(self._counters.get((tenant_id, period), {}))
