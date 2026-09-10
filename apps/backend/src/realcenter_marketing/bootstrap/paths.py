"""Explicit runtime locations. Data paths retain their pre-migration identity."""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    workspace: Path
    data_root: Path
    static_root: Path

    @classmethod
    def discover(cls, root=None):
        workspace = next((p for p in Path(__file__).resolve().parents if (p / 'apps/backend/pyproject.toml').is_file()), Path.cwd())
        configured = root if root is not None else os.environ.get('REALCENTER_DATA_ROOT')
        data = Path(configured).resolve() if configured else workspace / 'realcenter-marketing-ai'
        if (data / 'apps/backend/pyproject.toml').is_file() and (data / 'realcenter-marketing-ai').is_dir():
            workspace, data = data, data / 'realcenter-marketing-ai'
        static = Path(os.environ.get('REALCENTER_STATIC_ROOT', workspace / 'apps/frontend/dist')).resolve()
        return cls(workspace.resolve(), data.resolve(), static)

    @property
    def demo_responses(self):
        legacy = self.data_root / 'templates/demo-responses.json'
        if legacy.is_file():
            return legacy
        from realcenter_marketing.infrastructure.resources import resources_root
        return resources_root() / 'demo/demo-responses.json'

    @property
    def catalog_sources(self):
        return [self.workspace / 'resources', self.workspace / 'docs', self.workspace / 'apps/backend/src', self.workspace / 'apps/frontend/src',
                self.data_root / 'src', self.data_root / 'agents', self.data_root / 'config',
                self.data_root / 'docs', self.data_root / 'brand']
