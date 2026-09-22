"""In-memory IdentityStore used by the offline suite.

The rules under test are the service's, not Postgres's, so the fast suite runs with no
database at all — which is what keeps CI able to build and smoke the image with the
network disabled. The Postgres adapter is covered separately by the integration tests,
which skip unless TEST_DATABASE_URL points at a real server.
"""
import threading

from realcenter_marketing.application.identity.model import Invite, Session, Tenant, User, now


class FakeIdentityStore:
    def __init__(self):
        self.tenants_by_id, self.users_by_id = {}, {}
        self.passwords, self.identities, self.roles = {}, {}, {}
        self.sessions, self.invites = {}, {}
        self.module_settings, self.created_stores, self.created_users = {}, {}, {}
        self._sequence, self._guard = 0, threading.Lock()

    def _next(self):
        with self._guard:
            self._sequence += 1
            return self._sequence

    # -- tenants ---------------------------------------------------------------

    def create_tenant(self, slug, name, root_path=None):
        tenant = Tenant(id=self._next(), slug=slug, name=name, root_path=root_path)
        self.tenants_by_id[tenant.id] = tenant
        self.created_stores[tenant.id] = now()
        return tenant

    def tenant(self, tenant_id):
        return self.tenants_by_id.get(tenant_id)

    def tenant_by_slug(self, slug):
        return next((t for t in self.tenants_by_id.values() if t.slug == slug), None)

    def tenants(self):
        return sorted(self.tenants_by_id.values(), key=lambda t: t.name)

    def set_tenant_status(self, tenant_id, status):
        current = self.tenants_by_id[tenant_id]
        self.tenants_by_id[tenant_id] = Tenant(current.id, current.slug, current.name,
                                               current.root_path, status)

    def members(self, tenant_id):
        return [(self.users_by_id[user_id], role)
                for (user_id, holder), role in self.roles.items() if holder == tenant_id]

    def modules(self, tenant_id):
        from realcenter_marketing.application.identity.modules import module_defaults
        return module_defaults(self.module_settings.get(tenant_id))

    def set_module(self, tenant_id, module, enabled):
        self.module_settings.setdefault(tenant_id, {})[module] = enabled

    def registration_counts(self, start, end):
        def count(values):
            return sum((start is None or at >= start) and at < end for at in values.values())
        return {'new_stores': count(self.created_stores), 'new_users': count(self.created_users)}

    def suspend(self, tenant_id):
        current = self.tenants_by_id[tenant_id]
        self.tenants_by_id[tenant_id] = Tenant(current.id, current.slug, current.name,
                                               current.root_path, 'suspended')

    # -- users -----------------------------------------------------------------

    def create_user(self, email, password_hash, name=''):
        user = User(id=self._next(), email=email, name=name)
        self.users_by_id[user.id] = user
        self.created_users[user.id] = now()
        self.passwords[user.id] = password_hash
        return user

    def user_by_email(self, email):
        return next((u for u in self.users_by_id.values() if u.email.lower() == email.lower()), None)

    def user_by_id(self, user_id):
        return self.users_by_id.get(user_id)

    def password_hash(self, user_id):
        return self.passwords.get(user_id)

    def set_password(self, user_id, password_hash):
        self.passwords[user_id] = password_hash

    def update_profile(self, user_id, email, name, phone):
        current = self.users_by_id[user_id]
        updated = User(current.id, email, name, current.status, phone)
        self.users_by_id[user_id] = updated
        return updated

    def touch_login(self, user_id):
        self.last_login = user_id

    # -- federated identities --------------------------------------------------

    def user_by_identity(self, provider, subject):
        user_id = self.identities.get((provider, subject))
        return self.users_by_id.get(user_id) if user_id else None

    def link_identity(self, user_id, provider, subject):
        self.identities[(provider, subject)] = user_id

    # -- membership ------------------------------------------------------------

    def grant(self, user_id, tenant_id, role):
        self.roles[(user_id, tenant_id)] = role

    def membership(self, user_id, tenant_id):
        return self.roles.get((user_id, tenant_id))

    def memberships(self, user_id):
        return [(self.tenants_by_id[tenant_id], role)
                for (holder, tenant_id), role in self.roles.items() if holder == user_id]

    def revoke(self, user_id, tenant_id):
        self.roles.pop((user_id, tenant_id), None)

    # -- sessions --------------------------------------------------------------

    def create_session(self, token_hash, user_id, tenant_id, role, csrf):
        stamp = now()
        session = Session(id=token_hash, user_id=user_id, tenant_id=tenant_id, role=role,
                          csrf=csrf, created_at=stamp, last_seen_at=stamp)
        self.sessions[token_hash] = session
        return session

    def session(self, token_hash):
        return self.sessions.get(token_hash)

    def touch_session(self, token_hash):
        current = self.sessions.get(token_hash)
        if current:
            self.sessions[token_hash] = Session(current.id, current.user_id, current.tenant_id,
                                                current.role, current.csrf, current.created_at, now())

    def age_session(self, token_hash, created_at=None, last_seen_at=None):
        """Test helper: move a session back in time instead of sleeping."""
        current = self.sessions[token_hash]
        self.sessions[token_hash] = Session(current.id, current.user_id, current.tenant_id,
                                            current.role, current.csrf,
                                            created_at or current.created_at,
                                            last_seen_at or current.last_seen_at)

    def drop_session(self, token_hash):
        self.sessions.pop(token_hash, None)

    def drop_user_sessions(self, user_id):
        for key in [k for k, s in self.sessions.items() if s.user_id == user_id]:
            self.sessions.pop(key)

    # -- invites ---------------------------------------------------------------

    def create_invite(self, token_hash, tenant_id, role, email, expires_at):
        self.invites[token_hash] = Invite(tenant_id=tenant_id, role=role, email=email,
                                          expires_at=expires_at)

    def invite(self, token_hash):
        return self.invites.get(token_hash)

    def consume_invite(self, token_hash):
        current = self.invites.get(token_hash)
        with self._guard:
            if current is None or current.used_at is not None:
                return False
            self.invites[token_hash] = Invite(current.tenant_id, current.role, current.email,
                                              current.expires_at, now())
            return True
