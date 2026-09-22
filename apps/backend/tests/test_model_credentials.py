import json

import pytest

from realcenter_marketing.bootstrap.settings import Settings
from realcenter_marketing.infrastructure import model_credentials as keys


def test_store_keys_are_isolated_and_override_inheritance_without_echoing(tmp_path, monkeypatch):
    platform, first, second = (tmp_path / name for name in ('platform', 'first', 'second'))
    platform.mkdir()
    monkeypatch.setenv('OPENAI_API_KEY', 'platform-test-key')
    keys.save(platform, first, {'openai': {'action': 'replace', 'key': 'store-test-key'}})
    assert Settings.load(first, env_root=platform).credential('openai') == 'store-test-key'
    assert Settings.load(second, env_root=platform).credential('openai') == 'platform-test-key'
    view = keys.public(platform, first, {'OPENAI_API_KEY': 'platform-test-key'})
    assert view['providers']['openai']['source'] == 'store'
    assert 'store-test-key' not in json.dumps(view)
    assert 'platform-test-key' not in json.dumps(view)
    assert not (first / '.model-keys').exists()
    keys.save(platform, first, {'openai': {'action': 'inherit'}})
    assert Settings.load(first, env_root=platform).credential('openai') == 'platform-test-key'


def test_tenant_files_cannot_override_platform_managed_credentials(tmp_path, monkeypatch):
    platform, tenant = tmp_path / 'platform', tmp_path / 'tenant'
    platform.mkdir()
    tenant.mkdir()
    monkeypatch.setenv('OPENAI_API_KEY', 'platform-test-key')
    (tenant / '.env').write_text('OPENAI_API_KEY=untrusted-key\nNVIDIA_BASE_URL=https://untrusted.test')
    keys.save(tenant, tenant, {'openai': {'action': 'replace', 'key': 'untrusted-key'}})
    settings = Settings.load(tenant, env_root=platform)
    assert settings.credential('openai') == 'platform-test-key'
    assert 'untrusted' not in settings.nvidia_base_url


@pytest.mark.parametrize('changes', [None, [], {}, {'unknown': {'action': 'replace', 'key': 'key'}},
    {'openai': {'action': 'replace', 'key': ''}}, {'openai': {'action': 'replace', 'key': 'bad\nkey'}},
    {'openai': {'action': 'unknown'}}, {'openai': {'action': 'replace', 'key': 12}}])
def test_invalid_key_edits_leave_existing_keys_intact(tmp_path, changes):
    tenant = tmp_path / 'tenant'
    keys.save(tmp_path, tenant, {'openai': {'action': 'replace', 'key': 'old-test-key'}})
    with pytest.raises(ValueError):
        keys.save(tmp_path, tenant, changes)
    assert keys.load(tmp_path, tenant)['openai'] == 'old-test-key'


def test_bad_storage_fails_instead_of_silently_billing_global_key(tmp_path):
    tenant = tmp_path / 'tenant'
    keys.save(tmp_path, tenant, {'openai': {'action': 'replace', 'key': 'test-key'}})
    next((tmp_path / '.model-keys').glob('*.json')).write_text('{bad json')
    with pytest.raises(ValueError, match='ler as chaves'):
        keys.load(tmp_path, tenant)
