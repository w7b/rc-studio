from pathlib import Path

import pytest

from realcenter_marketing.infrastructure.agents_sdk.demo import DemoModel
from realcenter_marketing.bootstrap.settings import Settings


@pytest.fixture
def root(tmp_path):
    """Self-contained brand fixture; never depends on private user assets or .env."""
    from PIL import Image
    project = tmp_path / 'project'
    brand = project / 'brand'
    (brand / 'references').mkdir(parents=True)
    for name in ('brand.md', 'colors.md', 'typography.md', 'visual-guidelines.md'):
        (brand / name).write_text('Brand Kit de teste. Informações comerciais pendentes.', encoding='utf-8')
    Image.new('RGB', (8, 8), 'white').save(brand / 'references' / 'fixture.png')
    # Style references are filtered by family, so the fixture declares its own.
    (brand / 'references' / 'families.json').write_text(
        '{"files": {"fixture.png": "produto"}}', encoding='utf-8')
    import shutil
    from realcenter_marketing.infrastructure.resources import resources_root, ROLE_FOLDERS
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
    from realcenter_marketing.bootstrap.paths import AppPaths
    return DemoModel(AppPaths.discover(root).demo_responses)
