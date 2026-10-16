"""Postgres implementation of IdentityStore."""
from studio_ai.application.identity.model import Invite, Session, Tenant, User

TENANT_COLUMNS = 'id, slug, name, root_path, status'
USER_COLUMNS = 'id, email, name, status, phone'


def _tenant(row):
    return Tenant(id=row[0], slug=row[1], name=row[2], root_path=row[3], status=row[4]) if row else None


def _user(row):
    return User(id=row[0], email=row[1], name=row[2], status=row[3],
                phone=row[4] if len(row) > 4 else '') if row else None


def _session(row):
    if row is None:
        return None
    return Session(id=row[0], user_id=row[1], tenant_id=row[2], role=row[3], csrf=row[4],
                   created_at=row[5], last_seen_at=row[6])


SESSION_COLUMNS = 'token_hash, user_id, tenant_id, role, csrf, created_at, last_seen_at'


class PostgresIdentityStore:
    def __init__(self, database):
        self.database = database

    def _one(self, sql, params=()):
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    def _all(self, sql, params=()):
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

    def _run(self, sql, params=()):
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.rowcount

    # -- tenants ---------------------------------------------------------------

    def tenant_by_slug(self, slug):
        return _tenant(self._one(f'SELECT {TENANT_COLUMNS} FROM tenants WHERE slug = %s', (slug,)))

    def tenant(self, tenant_id):
        return _tenant(self._one(f'SELECT {TENANT_COLUMNS} FROM tenants WHERE id = %s', (tenant_id,)))

    def tenants(self):
        return [_tenant(row) for row in self._all(f'SELECT {TENANT_COLUMNS} FROM tenants ORDER BY name')]

    def create_tenant(self, slug, name, root_path=None):
        return _tenant(self._one(
            f'INSERT INTO tenants (slug, name, root_path) VALUES (%s, %s, %s) RETURNING {TENANT_COLUMNS}',
            (slug, name, root_path)))

    def set_tenant_status(self, tenant_id, status):
        self._run('UPDATE tenants SET status = %s WHERE id = %s', (status, tenant_id))

    def modules(self, tenant_id):
        from studio_ai.application.identity.modules import module_defaults
        row = self._one('SELECT modules FROM tenants WHERE id = %s', (tenant_id,))
        return module_defaults(row[0] if row else None)

    def set_module(self, tenant_id, module, enabled):
        # Updating one JSON key in SQL preserves concurrent edits to other modules.
        self._run('UPDATE tenants SET modules = jsonb_set(modules, ARRAY[%s], to_jsonb(%s::boolean)) '
                  'WHERE id = %s', (module, enabled, tenant_id))

    def registration_counts(self, start, end):
        tenants = self._one('SELECT count(*) FROM tenants WHERE (%s::timestamptz IS NULL OR created_at >= %s) '
                            'AND created_at < %s', (start, start, end))[0]
        users = self._one('SELECT count(*) FROM users WHERE (%s::timestamptz IS NULL OR created_at >= %s) '
                          'AND created_at < %s', (start, start, end))[0]
        return {'new_stores': tenants, 'new_users': users}

    def members(self, tenant_id):
        rows = self._all(
            'SELECT u.id, u.email, u.name, u.status, u.phone, m.role FROM memberships m '
            'JOIN users u ON u.id = m.user_id WHERE m.tenant_id = %s ORDER BY u.email',
            (tenant_id,))
        return [(_user(row[:5]), row[5]) for row in rows]

    # -- users -----------------------------------------------------------------

    def user_by_email(self, email):
        return _user(self._one(f'SELECT {USER_COLUMNS} FROM users WHERE lower(email) = lower(%s)', (email,)))

    def user_by_id(self, user_id):
        return _user(self._one(f'SELECT {USER_COLUMNS} FROM users WHERE id = %s', (user_id,)))

    def password_hash(self, user_id):
        row = self._one('SELECT password_hash FROM users WHERE id = %s', (user_id,))
        return row[0] if row else None

    def create_user(self, email, password_hash, name=''):
        return _user(self._one(
            f'INSERT INTO users (email, password_hash, name) VALUES (%s, %s, %s) RETURNING {USER_COLUMNS}',
            (email, password_hash, name)))

    def set_password(self, user_id, password_hash):
        self._run('UPDATE users SET password_hash = %s WHERE id = %s', (password_hash, user_id))

    def update_profile(self, user_id, email, name, phone):
        return _user(self._one(
            f'UPDATE users SET email = %s, name = %s, phone = %s WHERE id = %s RETURNING {USER_COLUMNS}',
            (email, name, phone, user_id)))

    def touch_login(self, user_id):
        self._run('UPDATE users SET last_login_at = now() WHERE id = %s', (user_id,))

    # -- federated identities --------------------------------------------------

    def user_by_identity(self, provider, subject):
        return _user(self._one(
            'SELECT u.id, u.email, u.name, u.status, u.phone FROM users u '
            'JOIN identities i ON i.user_id = u.id WHERE i.provider = %s AND i.subject = %s',
            (provider, subject)))

    def link_identity(self, user_id, provider, subject):
        self._run('INSERT INTO identities (provider, subject, user_id) VALUES (%s, %s, %s) '
                  'ON CONFLICT (provider, subject) DO UPDATE SET user_id = EXCLUDED.user_id',
                  (provider, subject, user_id))

    # -- membership ------------------------------------------------------------

    def membership(self, user_id, tenant_id):
        row = self._one('SELECT role FROM memberships WHERE user_id = %s AND tenant_id = %s',
                        (user_id, tenant_id))
        return row[0] if row else None

    def memberships(self, user_id):
        rows = self._all(
            'SELECT t.id, t.slug, t.name, t.root_path, t.status, m.role FROM memberships m '
            'JOIN tenants t ON t.id = m.tenant_id WHERE m.user_id = %s ORDER BY t.name', (user_id,))
        return [(_tenant(row[:5]), row[5]) for row in rows]

    def grant(self, user_id, tenant_id, role):
        self._run('INSERT INTO memberships (user_id, tenant_id, role) VALUES (%s, %s, %s) '
                  'ON CONFLICT (user_id, tenant_id) DO UPDATE SET role = EXCLUDED.role',
                  (user_id, tenant_id, role))

    def revoke(self, user_id, tenant_id):
        self._run('DELETE FROM memberships WHERE user_id = %s AND tenant_id = %s',
                  (user_id, tenant_id))

    # -- sessions --------------------------------------------------------------

    def create_session(self, token_hash, user_id, tenant_id, role, csrf):
        return _session(self._one(
            'INSERT INTO sessions (token_hash, user_id, tenant_id, role, csrf) '
            f'VALUES (%s, %s, %s, %s, %s) RETURNING {SESSION_COLUMNS}',
            (token_hash, user_id, tenant_id, role, csrf)))

    def session(self, token_hash):
        return _session(self._one(f'SELECT {SESSION_COLUMNS} FROM sessions WHERE token_hash = %s',
                                  (token_hash,)))

    def touch_session(self, token_hash):
        self._run('UPDATE sessions SET last_seen_at = now() WHERE token_hash = %s', (token_hash,))

    def drop_session(self, token_hash):
        self._run('DELETE FROM sessions WHERE token_hash = %s', (token_hash,))

    def drop_user_sessions(self, user_id):
        self._run('DELETE FROM sessions WHERE user_id = %s', (user_id,))

    # -- invites ---------------------------------------------------------------

    def create_invite(self, token_hash, tenant_id, role, email, expires_at):
        self._run('INSERT INTO invites (token_hash, tenant_id, role, email, expires_at) '
                  'VALUES (%s, %s, %s, %s, %s)', (token_hash, tenant_id, role, email, expires_at))

    def invite(self, token_hash):
        row = self._one('SELECT tenant_id, role, email, expires_at, used_at FROM invites '
                        'WHERE token_hash = %s', (token_hash,))
        if row is None:
            return None
        return Invite(tenant_id=row[0], role=row[1], email=row[2], expires_at=row[3], used_at=row[4])

    def consume_invite(self, token_hash):
        """A conditional update is the claim: if two people open the same link, the
        second one updates no rows and is refused."""
        return self._run('UPDATE invites SET used_at = now() WHERE token_hash = %s AND used_at IS NULL',
                         (token_hash,)) == 1
