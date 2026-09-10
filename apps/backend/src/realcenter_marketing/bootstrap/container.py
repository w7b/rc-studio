"""Connect the HTTP adapter to configured application and infrastructure objects."""
from dataclasses import dataclass
from realcenter_marketing.application.queries import StudioQueries
from realcenter_marketing.infrastructure.queries import LocalStudioQueries
from realcenter_marketing.infrastructure.system_catalog import SystemCatalog
from realcenter_marketing.infrastructure.process_lease import ProcessLease
from .paths import AppPaths
from .services import CampaignService
from .settings import Settings


@dataclass
class Container:
    paths: AppPaths
    service: object
    queries: StudioQueries
    catalog: SystemCatalog
    lease: ProcessLease

    def public_config(self):
        settings = Settings.load(self.paths.data_root)
        return {'configured': bool(settings.model and settings.api_key.get_secret_value()),
                'model': settings.model, 'image_model': settings.image_model}

    def close(self):
        try:
            self.service.close()
            self.catalog.close()
        finally:
            self.lease.close()


def build_container(root=None):
    paths = AppPaths.discover(root)
    lease = ProcessLease(paths.data_root).acquire()
    try:
        service = CampaignService(paths.data_root)
        # For a standalone data root, index its own sources in addition to the app.
        catalog = SystemCatalog(paths.data_root, sources=paths.catalog_sources, workspace=paths.workspace)
        return Container(paths, service, LocalStudioQueries(paths.data_root), catalog, lease)
    except BaseException:
        lease.close()
        raise
