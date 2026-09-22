"""Identity values. Pure data: no storage, no framework, no I/O."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# A session dies twice: after an absolute age, and after a stretch of silence. The first
# bounds how long a stolen cookie is useful, the second covers the shared counter left
# logged in at the store.
ABSOLUTE_LIFETIME = timedelta(hours=12)
IDLE_LIFETIME = timedelta(hours=2)
ROTATE_AFTER = timedelta(minutes=30)
INVITE_LIFETIME = timedelta(days=7)

# DEFAULT and PAID gate quota and features; OWNER gates the platform itself.
# Note: DEFAULT/PAID describe a subscription, which is a property of the store, while
# OWNER describes a person. They share one column for now; if billing ever moves to
# the store, tenants.plan is where DEFAULT/PAID belong.
ROLES = ('DEFAULT', 'PAID', 'OWNER')
PAID_ROLES = ('PAID', 'OWNER')


def now():
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Tenant:
    id: int
    slug: str
    name: str
    root_path: str | None = None
    status: str = 'active'

    @property
    def active(self):
        return self.status == 'active'


@dataclass(frozen=True)
class User:
    id: int
    email: str
    name: str = ''
    status: str = 'active'
    phone: str = ''


@dataclass(frozen=True)
class Session:
    id: str
    user_id: int
    tenant_id: int
    role: str
    csrf: str
    created_at: datetime
    last_seen_at: datetime

    def expired(self, at=None):
        at = at or now()
        return at - self.created_at >= ABSOLUTE_LIFETIME or at - self.last_seen_at >= IDLE_LIFETIME

    def stale(self, at=None):
        """A live session whose identifier has been in use long enough to rotate."""
        return (at or now()) - self.created_at >= ROTATE_AFTER


@dataclass(frozen=True)
class Invite:
    tenant_id: int
    role: str
    email: str
    expires_at: datetime
    used_at: datetime | None = None

    def usable(self, at=None):
        return self.used_at is None and (at or now()) < self.expires_at


@dataclass(frozen=True)
class Principal:
    """Who is asking, and on behalf of which store."""
    user: User
    tenant: Tenant
    role: str
    session_id: str
    csrf: str

    @property
    def is_paid(self):
        """Full quota and every format. OWNER is paid by definition."""
        return self.role in PAID_ROLES

    @property
    def is_owner(self):
        return self.role == 'OWNER'


@dataclass
class OAuthProfile:
    """What an OpenID provider asserts about the person signing in."""
    provider: str
    subject: str
    email: str
    email_verified: bool
    name: str = ''
    raw: dict = field(default_factory=dict)
