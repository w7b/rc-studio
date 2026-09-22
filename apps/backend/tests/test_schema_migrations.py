import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from realcenter_marketing.infrastructure.identity.database import Database, SCHEMA

URL = os.environ.get('TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='TEST_DATABASE_URL não configurada')


@pytest.fixture
def migration_url():
    schema = 'migration_' + uuid.uuid4().hex
    with psycopg.connect(URL, autocommit=True) as connection:
        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    try:
        yield make_conninfo(URL, options=f'-c search_path={schema}')
    finally:
        with psycopg.connect(URL, autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def test_fresh_database_records_versions_only_once(migration_url):
    database = Database(migration_url).open()
    try:
        with database.connection() as connection:
            before = connection.execute('SELECT version, applied_at FROM schema_migrations ORDER BY version').fetchall()
        database.apply_schema()
        with database.connection() as connection:
            after = connection.execute('SELECT version, applied_at FROM schema_migrations ORDER BY version').fetchall()
            connection.execute('SELECT heartbeat_at FROM jobs')
        assert before == after
        assert [row[0] for row in before] == ['001_baseline', '002_membership_roles']
    finally:
        database.close()


def test_legacy_role_constraint_and_existing_rows_are_migrated(migration_url):
    with psycopg.connect(migration_url, autocommit=True) as connection:
        legacy = SCHEMA.read_text(encoding='utf-8').replace("'DEFAULT', 'PAID', 'OWNER'", "'owner', 'manager', 'editor'")
        connection.execute(legacy)
        tenant = connection.execute("INSERT INTO tenants (slug, name) VALUES ('legacy', 'Legacy') RETURNING id").fetchone()[0]
        for role in ('owner', 'manager', 'editor'):
            user = connection.execute('INSERT INTO users (email) VALUES (%s) RETURNING id', (role + '@test.invalid',)).fetchone()[0]
            connection.execute('INSERT INTO memberships VALUES (%s, %s, %s)', (user, tenant, role))
            connection.execute('INSERT INTO sessions (token_hash, user_id, tenant_id, role, csrf) VALUES (%s,%s,%s,%s,%s)',
                               (role, user, tenant, role, 'csrf'))
            connection.execute("INSERT INTO invites (token_hash, tenant_id, role, expires_at) VALUES (%s,%s,%s,now() + interval '1 day')",
                               (role, tenant, role))
    database = Database(migration_url).open()
    try:
        with database.connection() as connection:
            for table in ('memberships', 'sessions', 'invites'):
                roles = connection.execute(sql.SQL('SELECT role FROM {} ORDER BY role').format(sql.Identifier(table))).fetchall()
                assert roles == [('DEFAULT',), ('OWNER',), ('PAID',)]
            connection.execute("UPDATE memberships SET role = 'PAID'")
            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute("UPDATE memberships SET role = 'editor'")
    finally:
        database.close()


def test_concurrent_boots_apply_each_migration_once(migration_url):
    def boot(_):
        database = Database(migration_url).open()
        database.close()
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(boot, range(2)))
    with psycopg.connect(migration_url) as connection:
        assert connection.execute('SELECT count(*) FROM schema_migrations').fetchone()[0] == 2


def test_failed_migration_rolls_back_schema_and_version(migration_url, tmp_path, monkeypatch):
    import realcenter_marketing.infrastructure.identity.database as module
    migrations = tmp_path / 'migrations'
    migrations.mkdir()
    (migrations / '001_broken.sql').write_text('CREATE TABLE should_rollback (id integer); SELECT missing_column;', encoding='utf-8')
    monkeypatch.setattr(module, 'MIGRATIONS', migrations, raising=False)
    database = Database(migration_url)
    try:
        with pytest.raises(psycopg.errors.UndefinedColumn):
            database.open()
        with psycopg.connect(migration_url) as connection:
            assert connection.execute("SELECT to_regclass('should_rollback')").fetchone()[0] is None
            if connection.execute("SELECT to_regclass('schema_migrations')").fetchone()[0]:
                assert connection.execute('SELECT count(*) FROM schema_migrations').fetchone()[0] == 0
    finally:
        database.close()
