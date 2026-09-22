from pathlib import Path

from realcenter_marketing.bootstrap.paths import AppPaths


def test_default_layout_keeps_platform_credentials_outside_tenants(monkeypatch):
    for name in ('REALCENTER_DATA_ROOT', 'REALCENTER_TENANTS_ROOT', 'REALCENTER_ENV_ROOT'):
        monkeypatch.delenv(name, raising=False)
    paths = AppPaths.discover()
    assert paths.data_root == paths.workspace / 'data/tenants/default'
    assert paths.tenants_root == paths.workspace / 'data/tenants'
    assert paths.env_root == paths.workspace / 'data/platform'
    assert not paths.env_root.is_relative_to(paths.tenants_root)
    # Services rediscover a resolved tenant root when loading Settings.
    assert AppPaths.discover(paths.data_root).env_root == paths.env_root


def test_explicit_fixture_and_legacy_roots_keep_their_configuration(tmp_path, monkeypatch):
    for name in ('REALCENTER_DATA_ROOT', 'REALCENTER_TENANTS_ROOT', 'REALCENTER_ENV_ROOT'):
        monkeypatch.delenv(name, raising=False)
    paths = AppPaths.discover(tmp_path)
    assert paths.data_root == paths.env_root == tmp_path
    assert paths.tenants_root == tmp_path / 'tenants'
    monkeypatch.setenv('REALCENTER_ENV_ROOT', str(tmp_path / 'platform'))
    monkeypatch.setenv('REALCENTER_TENANTS_ROOT', str(tmp_path / 'stores'))
    paths = AppPaths.discover(tmp_path)
    assert paths.env_root == tmp_path / 'platform'
    assert paths.tenants_root == tmp_path / 'stores'


def test_checkout_root_resolves_to_canonical_layout(monkeypatch):
    for name in ('REALCENTER_DATA_ROOT', 'REALCENTER_TENANTS_ROOT', 'REALCENTER_ENV_ROOT'):
        monkeypatch.delenv(name, raising=False)
    workspace = Path(__file__).resolve().parents[3]
    paths = AppPaths.discover(workspace)
    assert paths.data_root == workspace / 'data/tenants/default'
    assert paths.env_root == workspace / 'data/platform'
