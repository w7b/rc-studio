"""Canonical storage, with explicit roots retained for existing installations."""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    workspace: Path
    data_root: Path
    static_root: Path
    env_root: Path = None
    _tenants_root: Path = None

    def __post_init__(self):
        if self.env_root is None:
            object.__setattr__(self, 'env_root', self.data_root)

    @classmethod
    def discover(cls, root=None):
        workspace = next((p for p in Path(__file__).resolve().parents if (p / 'apps/backend/pyproject.toml').is_file()), Path.cwd())
        configured = root if root is not None else os.environ.get('REALCENTER_DATA_ROOT')
        data = Path(configured).resolve() if configured else None
        if data is not None and (data / 'apps/backend/pyproject.toml').is_file():
            workspace, data = data, None
        explicit = data is not None
        data = data if explicit else workspace / 'data/tenants/default'
        canonical = data.is_relative_to(workspace / 'data/tenants')
        static = Path(os.environ.get('REALCENTER_STATIC_ROOT', workspace / 'apps/frontend/dist')).resolve()
        # Credentials are read from env_root, which a multi-tenant deployment points at the
        # platform directory. A tenant's own data root must never supply them: a writable
        # .env there could redirect NVIDIA_BASE_URL and receive the operator's API key.
        configured_env = os.environ.get('REALCENTER_ENV_ROOT')
        env = Path(configured_env).resolve() if configured_env else (workspace / 'data/platform' if canonical else data)
        tenants = workspace / 'data/tenants' if canonical else data / 'tenants'
        return cls(workspace.resolve(), data.resolve(), static, env.resolve(), tenants.resolve())

    @property
    def demo_responses(self):
        legacy = self.data_root / 'templates/demo-responses.json'
        if legacy.is_file():
            return legacy
        from realcenter_marketing.infrastructure.resources import resources_root
        return resources_root() / 'demo/demo-responses.json'

    @property
    def tenants_root(self):
        """Where stores created from now on keep their data. A store registered with an
        explicit root_path stays where it is; this is only the default for new ones."""
        configured = os.environ.get('REALCENTER_TENANTS_ROOT')
        return Path(configured).resolve() if configured else (self._tenants_root or self.data_root / 'tenants')
