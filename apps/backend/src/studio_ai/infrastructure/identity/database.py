"""Postgres pool and ordered, transactional plain-SQL migrations."""
import os
import threading
from pathlib import Path

SCHEMA = Path(__file__).with_name('schema.sql')
MIGRATIONS = Path(__file__).with_name('migrations')


def database_url():
    """Local auto mode stays compatible; Docker explicitly requires shared mode.

    Missing/invalid shared configuration must never silently disable authentication.
    Build a libpq connection string from separate fields instead of interpolating a
    password into a URI (characters such as @, / and # would change its meaning).
    """
    mode = os.environ.get('REALCENTER_DEPLOYMENT_MODE', 'auto').strip().lower()
    if mode not in ('auto', 'shared', 'standalone'):
        raise ValueError('REALCENTER_DEPLOYMENT_MODE deve ser auto, shared ou standalone')
    if mode == 'standalone':
        return None
    configured = (os.environ.get('DATABASE_URL') or '').strip()
    if configured:
        return configured
    if mode == 'auto':
        return None
    from psycopg.conninfo import make_conninfo
    fields = {'host': 'PGHOST', 'port': 'PGPORT', 'dbname': 'PGDATABASE',
              'user': 'PGUSER', 'password': 'PGPASSWORD'}
    values = {field: os.environ.get(variable, '') for field, variable in fields.items()}
    missing = [variable for field, variable in fields.items() if not values[field]]
    if missing:
        raise ValueError('Modo compartilhado exige DATABASE_URL ou: ' + ', '.join(missing))
    return make_conninfo(**values)


class Database:
    def __init__(self, url, min_size=1, max_size=8):
        from psycopg_pool import ConnectionPool
        self.url = url
        self._pool = ConnectionPool(url, min_size=min_size, max_size=max_size, open=False,
                                    kwargs={'autocommit': True})
        self._ready = threading.Event()

    def open(self, timeout=15):
        try:
            self._pool.open(wait=True, timeout=timeout)
            self.apply_schema()
        except BaseException:
            self._pool.close()
            raise
        self._ready.set()
        return self

    def apply_schema(self):
        with self.connection() as connection, connection.transaction(), connection.cursor() as cursor:
            # Web and worker may boot simultaneously, including on an empty database.
            cursor.execute('SELECT pg_advisory_xact_lock(724190021)')
            cursor.execute('CREATE TABLE IF NOT EXISTS schema_migrations ('
                           'version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())')
            cursor.execute('SELECT version FROM schema_migrations')
            applied = {row[0] for row in cursor.fetchall()}
            for migration in sorted(MIGRATIONS.glob('[0-9]*.sql')):
                if migration.stem not in applied:
                    cursor.execute(migration.read_text(encoding='utf-8'))
                    cursor.execute('INSERT INTO schema_migrations (version) VALUES (%s)',
                                   (migration.stem,))

    def connection(self):
        return self._pool.connection()

    def close(self):
        self._pool.close()
