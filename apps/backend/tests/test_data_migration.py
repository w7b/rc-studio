import hashlib
from pathlib import Path

import pytest

from script_loader import load_script
from realcenter_marketing.infrastructure.persistence.filesystem import media_catalog


def migration():
    assert (Path(__file__).resolve().parents[3] / 'scripts/migrate_data.py').is_file()
    return load_script('migrate_data')


def fixture(tmp_path):
    legacy, target = tmp_path / 'legacy', tmp_path / 'data'
    (legacy / 'brand/products').mkdir(parents=True)
    (legacy / 'brand/products/product.png').write_bytes(b'product')
    (legacy / 'campaigns').mkdir()
    (legacy / 'campaigns/.studio.lock').write_bytes(b'0')
    (legacy / 'tenant.json').write_text('{}')
    (legacy / '.env').write_text('OPENAI_API_KEY=secret-fixture')
    (legacy / 'tenants/second/brand').mkdir(parents=True)
    (legacy / 'tenants/second/brand/brand.md').write_text('second')
    return legacy, target


def test_plan_has_no_side_effects_and_apply_preserves_sources_and_media_ids(tmp_path):
    legacy, target = fixture(tmp_path)
    script = migration()
    plan = script.plan_migration(legacy, target, 'first')
    assert not target.exists()
    before_ids = set(media_catalog(legacy))
    first = script.apply_migration(plan)
    assert first['copied'] == 4
    assert (target / 'platform/.env').read_text() == 'OPENAI_API_KEY=secret-fixture'
    assert not (target / 'tenants/first/.env').exists()
    assert not (target / 'tenants/first/campaigns/.studio.lock').exists()
    assert (target / 'tenants/second/brand/brand.md').read_text() == 'second'
    assert set(media_catalog(target / 'tenants/first')) == before_ids
    assert (legacy / 'brand/products/product.png').read_bytes() == b'product'
    assert script.apply_migration(plan)['copied'] == 0


def test_conflicting_destination_aborts_before_any_copy(tmp_path):
    legacy, target = fixture(tmp_path)
    (target / 'tenants/first').mkdir(parents=True)
    (target / 'tenants/first/tenant.json').write_text('different')
    script = migration()
    with pytest.raises(ValueError, match='diferente'):
        script.plan_migration(legacy, target, 'first')
    assert not (target / 'platform').exists()


def test_source_change_after_plan_is_rejected(tmp_path):
    legacy, target = fixture(tmp_path)
    script = migration()
    plan = script.plan_migration(legacy, target, 'first')
    (legacy / 'tenant.json').write_text('{"changed":true}')
    with pytest.raises(ValueError, match='origem'):
        script.apply_migration(plan)
    assert not target.exists()


@pytest.mark.parametrize('slug', ['../escape', 'UPPER', '', 'two/stores'])
def test_invalid_slug_is_rejected(tmp_path, slug):
    legacy, target = fixture(tmp_path)
    with pytest.raises(ValueError, match='slug'):
        migration().plan_migration(legacy, target, slug)


def test_destination_cannot_overlap_source(tmp_path):
    legacy, _ = fixture(tmp_path)
    with pytest.raises(ValueError, match='sobrepor'):
        migration().plan_migration(legacy, legacy / 'new', 'first')


def test_private_model_key_names_follow_new_runtime_roots(tmp_path):
    legacy, target = fixture(tmp_path)
    keys = legacy / '.model-keys'
    keys.mkdir()
    old_hash = hashlib.sha256(b'/app/realcenter-marketing-ai').hexdigest()
    new_hash = hashlib.sha256(b'/app/data/tenants/first').hexdigest()
    (keys / f'{old_hash}.json').write_bytes(b'{"openai":"fixture"}')
    script = migration()
    script.apply_migration(script.plan_migration(legacy, target, 'first'))
    assert (target / f'platform/.model-keys/{new_hash}.json').read_bytes() == b'{"openai":"fixture"}'
    assert not (target / f'platform/.model-keys/{old_hash}.json').exists()


def test_cli_plan_does_not_print_credentials(tmp_path, capsys):
    legacy, target = fixture(tmp_path)
    assert migration().main(['--legacy-root', str(legacy), '--data-root', str(target),
                             '--legacy-tenant', 'first']) == 0
    output = capsys.readouterr().out
    assert 'secret-fixture' not in output
    assert '4' in output
    assert not target.exists()
