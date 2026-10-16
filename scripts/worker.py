"""Campaign worker: a second process of the same image.

Runs jobs claimed from Postgres so that restarting the web process no longer kills a
campaign in flight. This is the cheap answer to "should we orchestrate with Kubernetes":
the problem was never scheduling across nodes, it was that execution lived inside the
request process.

    DATABASE_URL=... python scripts/worker.py
"""
import argparse
import os
import signal
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/backend/src'))

from studio_ai.application.errors import BusyError  # noqa: E402
from studio_ai.bootstrap.platform import build_identity  # noqa: E402
from studio_ai.bootstrap.registry import TenantRegistry  # noqa: E402
from studio_ai.bootstrap.paths import AppPaths  # noqa: E402
from studio_ai.infrastructure.identity.jobs import PostgresJobQueue  # noqa: E402

IDLE_SECONDS = 2
HEARTBEAT_SECONDS = 20
LEASE_SECONDS = 120
# Filesystem mtime and time.time() are not guaranteed to use the same clock source.
# Allow small skew, but reject timestamps clearly in the future as a broken clock.
CLOCK_SKEW_SECONDS = 3
DRAIN_SECONDS = 4800
running = True


def stop(*_):
    global running
    running = False


def execute(registry, job):
    context = registry.context(job['tenant_slug'], job['root_path'],
                               tenant_id=job['tenant_id'], role='OWNER')
    # resume is synchronous and neither reserves quota nor dispatches another job.
    return context.service.resume(job['kind'], job['run_id'], job['payload'])


def run_once(registry, queue, heartbeat_path=None):
    """Claim and process one job; False means there was no work."""
    job = queue.claim()
    if job is None:
        return False
    owner = job['claimed_by']
    finished = threading.Event()

    def pulse():
        while not finished.wait(HEARTBEAT_SECONDS):
            try:
                if not queue.heartbeat(job['id'], worker=owner):
                    return
                if heartbeat_path is not None:
                    heartbeat_path.touch()
            except Exception as exc:
                print(f'Heartbeat do job {job["id"]} falhou: {exc}', flush=True)

    heartbeat = threading.Thread(target=pulse, name='job-heartbeat', daemon=True)
    heartbeat.start()
    try:
        execute(registry, job)
    except BusyError:
        queue.requeue(job['id'], worker=owner)
    except Exception as exc:
        # Provider errors and missing mounts are terminal, never automatic refunds.
        queue.finish(job['id'], error=f'{type(exc).__name__}: {exc}'[:500], worker=owner)
    else:
        queue.finish(job['id'], worker=owner)
    finally:
        finished.set()
        heartbeat.join()
    return True


def healthcheck(queue, heartbeat_path):
    queue.pending()  # Requires a live database and a readable jobs table.
    age = time.time() - heartbeat_path.stat().st_mtime
    if not -CLOCK_SKEW_SECONDS <= age < LEASE_SECONDS:
        raise RuntimeError('Heartbeat do worker expirado')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Worker durável do Studio')
    parser.add_argument('--healthcheck', action='store_true')
    args = parser.parse_args(argv)
    identity = build_identity()
    if identity is None:
        raise SystemExit('Defina DATABASE_URL: o worker só existe na implantação compartilhada.')
    queue = PostgresJobQueue(identity.database)
    heartbeat_path = Path(os.environ.get('WORKER_HEARTBEAT_FILE',
                                         str(Path(tempfile.gettempdir()) / 'studio-worker-heartbeat')))
    if args.healthcheck:
        try:
            healthcheck(queue, heartbeat_path)
        finally:
            identity.close()
        return
    paths = AppPaths.discover(None)
    registry = TenantRegistry(paths.tenants_root, quota_for=None, queue_for=None, env_root=paths.env_root)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    recovered = queue.requeue_stale()
    queue.abandon_exhausted()
    heartbeat_path.touch()
    print(f'Worker iniciado. Trabalhos recuperados: {recovered}', flush=True)
    try:
        while running:
            queue.requeue_stale()
            queue.abandon_exhausted()
            heartbeat_path.touch()
            if not run_once(registry, queue, heartbeat_path):
                time.sleep(IDLE_SECONDS)
        # Signals only stop admission; the synchronous current job has already drained.
        registry.close(timeout=DRAIN_SECONDS)
    finally:
        heartbeat_path.unlink(missing_ok=True)
        identity.close()
        print('Worker encerrado.', flush=True)


if __name__ == '__main__':
    main()
