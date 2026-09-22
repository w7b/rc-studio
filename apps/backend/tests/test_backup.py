import tarfile

from script_loader import load_script

backup = load_script('backup')


def test_backup_includes_platform_model_keys_without_legacy_brand(tmp_path):
    data = tmp_path / 'data'
    keys = data / '.model-keys'
    keys.mkdir(parents=True)
    (keys / 'tenant.json').write_text('{"openai":"test-only"}')
    store = data / 'tenants' / 'shop'
    (store / 'brand').mkdir(parents=True)
    (store / 'brand' / 'brand.md').write_text('brand')
    destination = tmp_path / 'backups'
    destination.mkdir()
    made = backup.archive_stores(destination, data / 'tenants', data)
    members = {}
    for path in made:
        with tarfile.open(path) as archive:
            for member in archive.getmembers():
                if member.isfile():
                    members[member.name] = archive.extractfile(member).read()
    assert members['data/.model-keys/tenant.json'] == b'{"openai":"test-only"}'
    assert members['shop/brand/brand.md'] == b'brand'


def test_backup_covers_separate_platform_configuration_root(tmp_path):
    data, platform, destination = [tmp_path / name for name in ('data', 'platform', 'backup')]
    (platform / '.model-keys').mkdir(parents=True)
    (platform / '.model-keys' / 'key.json').write_text('{}')
    destination.mkdir()
    made = backup.archive_stores(destination, data / 'tenants', data, platform_root=platform)
    with tarfile.open(made[0]) as archive:
        assert 'platform/.model-keys/key.json' in archive.getnames()


def test_backup_covers_platform_env_consultations_and_deduplicates_default_store(tmp_path):
    data, platform, destination = [tmp_path / name for name in ('data', 'platform', 'backup')]
    store = data / 'tenants/default'
    (store / 'consultations/one').mkdir(parents=True)
    (store / 'consultations/one/events.jsonl').write_text('{}')
    (store / 'brand').mkdir()
    platform.mkdir()
    (platform / '.env').write_text('PRIVATE_FIXTURE=1')
    destination.mkdir()
    made = backup.archive_stores(destination, data / 'tenants', store, platform_root=platform)
    assert len(made) == 2
    members = []
    for path in made:
        with tarfile.open(path) as archive:
            members.extend(archive.getnames())
    assert 'platform/.env' in members
    assert members.count('default/consultations/one/events.jsonl') == 1


def test_tenant_named_platform_does_not_overwrite_platform_backup(tmp_path):
    data, destination = tmp_path / 'data', tmp_path / 'backup'
    store, platform = data / 'tenants/platform', data / 'platform'
    (store / 'brand').mkdir(parents=True)
    (store / 'brand/brand.md').write_text('brand')
    platform.mkdir()
    (platform / '.env').write_text('PRIVATE_FIXTURE=1')
    destination.mkdir()
    made = backup.archive_stores(destination, data / 'tenants', store, platform_root=platform)
    assert len(set(made)) == 2
    assert all(path.is_file() for path in made)
