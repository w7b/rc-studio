import copy


class FakeJobQueue:
    """Tenant-bound queue with explicit transitions, no scheduler or providers."""
    def __init__(self):
        self.jobs = []

    def enqueue(self, kind, payload, run_id):
        job_id = len(self.jobs) + 1
        self.jobs.append(dict(id=job_id, kind=kind, payload=copy.deepcopy(payload),
                              run_id=run_id, status='queued'))
        return job_id

    def active(self):
        return [dict(id=j['id'], run_id=j['run_id'], status=j['status'])
                for j in self.jobs if j['status'] in ('queued', 'running')]

    def pending(self):
        return len(self.active())
