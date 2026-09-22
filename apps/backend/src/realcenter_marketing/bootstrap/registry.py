"""One application context per store, created on demand.

The single most important property here is that a store's data root never comes from the
request. It is derived from the session's tenant, so the containment checks that already
exist in the persistence layer keep working — they just point at the right root.

That matters more than it looks: media ids are sha256 of a path relative to the data
root, so two stores holding `brand/logo/logo.png` produce the *same* id, and reference
ids are sha256 of the file's own bytes. Identifiers collide by construction. The only
thing standing between one store and another's files is that resolution always happens
against the session's root, and never by searching.
"""
import threading
from collections import OrderedDict
from dataclasses import dataclass, replace

from realcenter_marketing.infrastructure.execution import ExecutionPool
from realcenter_marketing.infrastructure import brand_kit, integrations_config, tenant_profile
from realcenter_marketing.infrastructure.queries import LocalStudioQueries
from .model_catalog import image_models, text_models
from .paths import AppPaths
from .services import CampaignService
from .settings import Settings, platform_values
from realcenter_marketing.application.errors import BusyError


@dataclass
class TenantContext:
    """What a request needs in order to answer for exactly one store."""
    slug: str
    paths: AppPaths
    service: object
    queries: LocalStudioQueries
    binding: tuple = ()

    @property
    def root(self):
        return self.paths.data_root

    def public_config(self):
        settings = Settings.load(self.paths.data_root, env_root=self.paths.env_root)
        text, images = text_models(settings), image_models(settings)
        # 'configured' stays a single yes/no for the form; the lists drive the picker.
        return {'configured': any(settings.has(option) for option in text),
                'model': settings.model, 'image_model': settings.image_model,
                'models': [option.public(settings.has(option)) for option in text],
                'image_models': [option.public(settings.has(option)) for option in images]}

    def brand_color(self):
        return tenant_profile.load(self.paths.data_root).brand_color

    def store_profile(self):
        return {'profile': tenant_profile.load(self.paths.data_root).model_dump(),
                'options': tenant_profile.options()}

    def save_store_profile(self, values):
        tenant_profile.save(self.paths.data_root, values)
        return self.store_profile()

    def consult(self, request):
        return self.service.consultations.run(request)

    def delete_image(self, key, source):
        scheduler, queue = self.service.scheduler, self.service.queue
        if queue is not None and queue.pending():
            raise BusyError('Aguarde a execução terminar antes de apagar uma imagem')
        if not scheduler.acquire():
            raise BusyError('Aguarde a execução terminar antes de apagar uma imagem')
        try:
            return self.queries.delete_image(key, source)
        finally:
            scheduler.release()

    def quota_summary(self):
        quota = getattr(self.service, 'quota', None)
        return quota.summary() if quota else None

    def run_state(self):
        queue = self.service.queue
        active = queue.active() if queue is not None else []
        statuses = {job['run_id']: job['status'] for job in active}
        local_id = self.service.active_id
        # snapshot() may return cache-owned dictionaries. Never mutate them.
        runs = [{**run, 'status': statuses.get(run['id'], run['status'])}
                for run in self.queries.runs(local_id)]
        return {'runs': runs, 'active_id': active[0]['run_id'] if active else local_id,
                'busy': self.service.busy or bool(active)}

    def brand_kit(self):
        return brand_kit.read(self.paths.data_root)

    def save_brand_kit(self, name, content):
        return brand_kit.write(self.paths.data_root, name, content)

    def seed_brand_kit(self, overwrite=False):
        profile = tenant_profile.load(self.paths.data_root)
        created = brand_kit.seed(self.paths.data_root, profile, overwrite=overwrite)
        return {**brand_kit.read(self.paths.data_root), 'created': created}

    def integrations(self):
        return integrations_config.public(self.paths.data_root)

    def save_integration(self, module, values):
        return integrations_config.save(self.paths.data_root, module, values)

    def validate_meta(self):
        return integrations_config.validate_meta(self.root)

    def close(self, timeout=None):
        return self.service.close(timeout)


class TenantRegistry:
    """Lazily built contexts, bounded by a shared execution pool.

    Eviction exists for the day there are hundreds of stores; with ten it never fires.
    A context is cheap because CampaignService receives every side effect through ports,
    so building one allocates closures and two paths, not connections.
    """

    def __init__(self, tenants_root, capacity=2, max_hot=32, quota_for=None, env_root=None,
                 queue_for=None):
        self.tenants_root = tenants_root
        self.env_root = env_root or AppPaths.discover().env_root
        # Supplied by the shared deployment; None leaves every store unmetered.
        self.quota_for = quota_for
        self.queue_for = queue_for
        self.pool = ExecutionPool(capacity=capacity)
        self.max_hot = max_hot
        self._contexts = OrderedDict()
        self._guard = threading.Lock()

    def root_for(self, slug, root_path=None):
        """A store registered with an explicit root keeps it, which is how the original
        installation stays exactly where it is instead of being moved."""
        if root_path:
            return AppPaths.discover(root_path).data_root
        return (self.tenants_root / slug).resolve()

    def integration_status(self, slug, root_path=None):
        return integrations_config.public(self.root_for(slug, root_path))

    def validate_meta(self, slug, root_path=None):
        return integrations_config.validate_meta(self.root_for(slug, root_path))

    def context(self, slug, root_path=None, tenant_id=None, role=None):
        root = self.root_for(slug, root_path)
        binding = (str(root), tenant_id, role)
        with self._guard:
            existing = self._contexts.get(slug)
            if existing is not None and existing.binding == binding:
                self._contexts.move_to_end(slug)
                return existing
        # The scheduler comes from the shared pool: one slot per store for fairness, one
        # worker ceiling for the machine and the bill.
        context = TenantContext(slug=slug, paths=replace(AppPaths.discover(root), env_root=self.env_root),
                                service=CampaignService(root, scheduler=self.pool.scheduler(slug),
                                                        env_root=self.env_root,
                                                        queue=self.queue_for(tenant_id, slug, root) if self.queue_for and tenant_id else None,
                                                        quota=self.quota_for(tenant_id, role) if self.quota_for and tenant_id else None),
                                queries=LocalStudioQueries(root, editor_config=lambda: platform_values(self.env_root)),
                                binding=binding)
        with self._guard:
            if slug in self._contexts and self._contexts[slug].binding == binding:
                # Both contexts borrow the SAME pool-owned scheduler. Closing the
                # unused wrapper would permanently close the winning store's slot.
                self._contexts.move_to_end(slug)
                return self._contexts[slug]
            self._contexts[slug] = context
            self._evict_cold()
            return context

    def _evict_cold(self):
        """Called under the guard. Never drops a store with work in flight, and never
        blocks a request thread waiting for one."""
        while len(self._contexts) > self.max_hot:
            slug, candidate = next(iter(self._contexts.items()))
            if candidate.service.busy or self.pool.position(slug) is not None:
                self._contexts.move_to_end(slug)
                return
            self._contexts.pop(slug)
            # Evict only the lightweight wrapper, not its pool-owned scheduler.
            # Future requests for this store reuse that scheduler.

    def close(self, timeout=None):
        with self._guard:
            contexts = list(self._contexts.values())
            self._contexts.clear()
        drained = self.pool.close(timeout)
        for context in contexts:
            context.close(timeout=0)
        return drained
