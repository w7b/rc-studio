from pathlib import Path

import pytest

from studio_ai.infrastructure.agents_sdk.demo import DemoModel
from studio_ai.bootstrap.settings import Settings


@pytest.fixture
def root(tmp_path):
    """Self-contained brand fixture; never depends on private user assets or .env."""
    from PIL import Image
    project = tmp_path / 'project'
    brand = project / 'brand'
    (brand / 'references').mkdir(parents=True)
    for name in ('brand.md', 'tone-of-voice.md', 'colors.md', 'typography.md',
                 'visual-guidelines.md'):
        (brand / name).write_text('Brand Kit de teste. Informações comerciais pendentes.', encoding='utf-8')
    Image.new('RGB', (8, 8), 'white').save(brand / 'references' / 'fixture.png')
    # Style references are filtered by family, so the fixture declares its own.
    (brand / 'references' / 'families.json').write_text(
        '{"files": {"fixture.png": "produto"}}', encoding='utf-8')
    import shutil
    from studio_ai.infrastructure.resources import resources_root, ROLE_FOLDERS
    resources = resources_root()
    for role in ('marketing_director', 'social_media', 'copywriter', 'creative', 'performance', 'marketing_analyst'):
        shutil.copytree(resources / 'agents' / ROLE_FOLDERS.get(role, role), project / 'agents' / role)
    shutil.copytree(resources / 'policies', project / 'config')
    shutil.copytree(resources / 'demo', project / 'templates')
    return project


@pytest.fixture
def settings(root):
    return Settings(project_root=root)


@pytest.fixture
def demo(root):
    from studio_ai.bootstrap.paths import AppPaths
    return DemoModel(AppPaths.discover(root).demo_responses)


@pytest.fixture
def isolated_root(root, tmp_path):
    """A data root that carries its own agents, policy and demo fixtures, so an HTTP
    server can be built against it without touching the developer's own data."""
    import shutil
    from studio_ai.infrastructure.resources import resources_root, ROLE_FOLDERS
    resources = resources_root()
    for role in ('marketing_director', 'social_media', 'copywriter', 'creative', 'performance', 'marketing_analyst'):
        shutil.copytree(resources / 'agents' / ROLE_FOLDERS.get(role, role), tmp_path / 'agents' / role)
    for source, name in ((root / 'brand', 'brand'), (resources / 'policies', 'config'), (resources / 'demo', 'templates')):
        shutil.copytree(source, tmp_path / name)
    return tmp_path
