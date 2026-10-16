"""Durable job queue on Postgres.

`FOR UPDATE SKIP LOCKED` is what makes this a queue rather than a table: several workers
can claim from it at once without blocking each other or handing the same row to two of
them. That is the piece that lets campaign execution move out of the web process, so a
deploy stops killing runs in flight — which is the real problem behind "should we use
Kubernetes", and it is solved here in one file instead of a cluster.
"""
import json
import socket
from uuid import uuid4


class PostgresJobQueue:
    def __init__(self, database):
        self.database = database
        self.worker = f'{socket.gethostname()}:{uuid4().hex}'

    def enqueue(self, tenant_id, tenant_slug, root_path, kind, payload, run_id=None):
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                'INSERT INTO jobs (tenant_id, tenant_slug, root_path, kind, payload, run_id) '
                'VALUES (%s, %s, %s, %s, %s, %s) RETURNING id',
                (tenant_id, tenant_slug, root_path, kind, json.dumps(payload), run_id))
            return cursor.fetchone()[0]

    def claim(self, max_attempts=3):
        """Take the oldest queued job, or None. Skipping locked rows keeps two workers
        from fighting over the same one."""
        with self.database.connection() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute(
                        'SELECT id, tenant_id, tenant_slug, root_path, kind, payload, run_id '
                        'FROM jobs WHERE status = %s AND attempts < %s '
                        'ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1',
                        ('queued', max_attempts))
                    row = cursor.fetchone()
                    if row is None:
                        return None
                    cursor.execute(
                        'UPDATE jobs SET status = %s, attempts = attempts + 1, claimed_by = %s, '
                        'claimed_at = now(), heartbeat_at = NULL WHERE id = %s',
                        ('running', self.worker, row[0]))
        payload = row[5] if isinstance(row[5], dict) else json.loads(row[5])
        return {'id': row[0], 'tenant_id': row[1], 'tenant_slug': row[2], 'root_path': row[3],
                'kind': row[4], 'payload': payload, 'run_id': row[6], 'claimed_by': self.worker}

    def finish(self, job_id, error=None, worker=None):
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE jobs SET status = %s, last_error = %s, finished_at = now() "
                "WHERE id = %s AND claimed_by = %s AND status = 'running'",
                ('failed' if error else 'done', (error or None), job_id, worker or self.worker))
            return cursor.rowcount == 1

    def requeue_stale(self, older_than_seconds=120):
        """A worker killed mid-job leaves its row as 'running' forever. Anything older
        than a full run timeout is put back, because the alternative is a job nobody ever
        picks up again."""
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE jobs SET status = 'queued', claimed_by = NULL, claimed_at = NULL, heartbeat_at = NULL "
                "WHERE status = 'running' AND coalesce(heartbeat_at, claimed_at) "
                "< now() - make_interval(secs => %s)",
                (older_than_seconds,))
            return cursor.rowcount

    def heartbeat(self, job_id, worker=None):
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE jobs SET heartbeat_at = now() WHERE id = %s "
                           "AND claimed_by = %s AND status = 'running'",
                           (job_id, worker or self.worker))
            return cursor.rowcount == 1

    def requeue(self, job_id, worker=None):
        """A busy local slot did no work: give back this attempt as well as the lease."""
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE jobs SET status = 'queued', attempts = greatest(attempts - 1, 0), "
                           "claimed_by = NULL, claimed_at = NULL, heartbeat_at = NULL "
                           "WHERE id = %s AND claimed_by = %s AND status = 'running'",
                           (job_id, worker or self.worker))
            return cursor.rowcount == 1

    def abandon_exhausted(self, max_attempts=3):
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE jobs SET status = 'failed', finished_at = now(), "
                           "last_error = 'Limite de tentativas atingido após perda do worker' "
                           "WHERE status = 'queued' AND attempts >= %s", (max_attempts,))
            return cursor.rowcount

    def active(self, tenant_id):
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT id, run_id, status FROM jobs WHERE tenant_id = %s "
                           "AND status IN ('queued', 'running') ORDER BY id", (tenant_id,))
            return [dict(zip(('id', 'run_id', 'status'), row)) for row in cursor.fetchall()]

    def for_tenant(self, tenant_id, tenant_slug, root_path):
        return TenantJobQueue(self, tenant_id, tenant_slug, root_path)

    def pending(self, tenant_id=None):
        clause, params = '', ()
        if tenant_id is not None:
            clause, params = ' AND tenant_id = %s', (tenant_id,)
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT count(*) FROM jobs WHERE status IN ('queued', 'running'){clause}", params)
            return cursor.fetchone()[0]


class TenantJobQueue:
    """Application-facing queue: tenant identity never comes from a request payload."""
    def __init__(self, queue, tenant_id, slug, root_path):
        self.queue, self.tenant_id = queue, tenant_id
        self.slug, self.root_path = slug, str(root_path)

    def enqueue(self, kind, payload, run_id):
        return self.queue.enqueue(self.tenant_id, self.slug, self.root_path, kind, payload, run_id)

    def active(self):
        return self.queue.active(self.tenant_id)

    def pending(self):
        return self.queue.pending(self.tenant_id)
