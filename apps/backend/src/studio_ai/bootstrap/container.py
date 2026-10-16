"""Connect the HTTP adapter to configured application and infrastructure objects."""
from dataclasses import dataclass
from studio_ai.application.queries import StudioQueries
from studio_ai.infrastructure.queries import LocalStudioQueries
from studio_ai.infrastructure.process_lease import ProcessLease
from .registry import TenantContext, TenantRegistry
from .model_catalog import image_models, text_models
from .paths import AppPaths
from .services import CampaignService
from .settings import Settings, platform_values
from studio_ai.infrastructure.cache import JsonCache


@dataclass
class Container:
    paths: AppPaths
    service: object
    queries: StudioQueries
    lease: ProcessLease
    registry: TenantRegistry = None
    cache: JsonCache = None

    @property
    def standalone(self):
        """The context used when there is no session to scope the request by."""
        return TenantContext(slug='local', paths=self.paths, service=self.service,
                             queries=self.queries)

    def public_config(self):
        settings = Settings.load(self.paths.data_root)
        text, images = text_models(settings), image_models(settings)
        # 'configured' stays a single yes/no for the form; the lists drive the picker.
        return {'configured': any(settings.has(option) for option in text),
                'model': settings.model, 'image_model': settings.image_model,
                'models': [option.public(settings.has(option)) for option in text],
                'image_models': [option.public(settings.has(option)) for option in images]}

    def close(self):
        try:
            if self.registry is not None:
                self.registry.close(timeout=0)
            self.service.close()
        finally:
            try:
                if self.cache is not None:
                    self.cache.close()
            finally:
                self.lease.close()

    def admin_metrics(self, store):
        from studio_ai.infrastructure.admin_metrics import collect_metrics
        return collect_metrics(store, self.registry.root_for)

    def model_keys(self, tenant):
        from studio_ai.infrastructure.model_credentials import public
        from .settings import platform_values
        return public(self.paths.env_root, self.registry.root_for(tenant.slug, tenant.root_path),
                      platform_values(self.paths.env_root))

    def save_model_keys(self, tenant, changes):
        from studio_ai.infrastructure.model_credentials import save
        save(self.paths.env_root, self.registry.root_for(tenant.slug, tenant.root_path), changes)
        if self.cache is not None:
            self.cache.delete(f'config:{tenant.slug}')
        return self.model_keys(tenant)


def build_container(root=None, quota_for=None, queue_for=None):
    paths = AppPaths.discover(root)
    lease = ProcessLease(paths.data_root).acquire()
    try:
        service = CampaignService(paths.data_root)
        registry = TenantRegistry(paths.tenants_root, quota_for=quota_for, env_root=paths.env_root,
                                  queue_for=queue_for)
        return Container(paths, service,
                         LocalStudioQueries(paths.data_root,
                                            editor_config=lambda: platform_values(paths.env_root)),
                         lease, registry, JsonCache.from_environment())
    except BaseException:
        lease.close()
        raise
