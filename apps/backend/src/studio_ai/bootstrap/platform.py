"""Composition root for the shared deployment.

Two shapes come out of here, decided only by DATABASE_URL:

standalone  no database, no login, one data root, bound to loopback. What the studio has
            always been, and what the offline smoke test exercises.
shared      Postgres-backed identity, one container per store, login required.

Keeping both in one process is deliberate: the single deployable promised by the modular
monolith decision survives, and the local workflow does not grow a database dependency.
"""
from dataclasses import dataclass

from studio_ai.application.identity.service import IdentityService
from studio_ai.infrastructure.identity.database import Database, database_url
from studio_ai.infrastructure.identity.oauth import GoogleOAuthProvider
from studio_ai.infrastructure.identity.passwords import ScryptHasher
from studio_ai.infrastructure.identity.rate_limit import MemoryRateLimiter
from studio_ai.infrastructure.identity.quotas import PostgresQuotaLedger, current_period
from studio_ai.infrastructure.identity.store import PostgresIdentityStore
from studio_ai.infrastructure.identity.jobs import PostgresJobQueue


@dataclass
class Identity:
    """Everything the HTTP layer needs to answer 'who is asking'."""
    service: IdentityService
    database: Database
    providers: dict
    ledger: object = None
    jobs: object = None

    def quota_for(self, tenant_id, role):
        from studio_ai.application.identity.quota import UsageQuota
        return UsageQuota(self.ledger, tenant_id, role, current_period) if self.ledger else None

    def queue_for(self, tenant_id, slug, root_path):
        return self.jobs.for_tenant(tenant_id, slug, root_path) if self.jobs is not None else None

    def close(self):
        self.database.close()


def build_identity(url=None):
    """None when the deployment is standalone. The caller treats that as 'no login'."""
    url = url or database_url()
    if not url:
        return None
    database = Database(url).open()
    providers = {}
    google = GoogleOAuthProvider.from_environment()
    if google is not None:
        providers[google.name] = google
    service = IdentityService(PostgresIdentityStore(database), ScryptHasher(),
                              MemoryRateLimiter(), providers)
    return Identity(service=service, database=database, providers=providers,
                    ledger=PostgresQuotaLedger(database), jobs=PostgresJobQueue(database))
