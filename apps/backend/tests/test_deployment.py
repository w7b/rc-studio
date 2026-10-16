"""Configuração de implantação, backup e layout de dados."""
import pytest
from pathlib import Path
from psycopg.conninfo import conninfo_to_dict
from studio_ai.infrastructure.identity.database import database_url
import tarfile
from script_loader import load_script
from studio_ai.bootstrap.paths import AppPaths
import hashlib
from studio_ai.infrastructure.persistence.filesystem import media_catalog


# ---- deployment_config -------------------------------------------------------

REPO = Path(__file__).resolve().parents[3]


def test_worker_has_its_own_healthcheck():
    compose = (REPO / 'compose.yaml').read_text(encoding='utf-8')
    worker = compose.split('\n  worker:', 1)[1].split('\n  db:', 1)[0]
    assert 'healthcheck:' in worker
    assert '"scripts/worker.py", "--healthcheck"' in worker


def test_production_and_ci_build_runtime_explicitly():
    compose = (REPO / 'compose.yaml').read_text(encoding='utf-8')
    assert compose.count('target: runtime') == 2
    ci = (REPO / '.github/workflows/tests.yml').read_text(encoding='utf-8')
    assert 'docker build --target runtime ' in ci


def test_dev_uses_its_own_project_storage_credentials_and_port():
    dev = (REPO / 'compose.dev.yaml').read_text(encoding='utf-8')
    assert 'name: studio-ai-dev' in dev
    assert dev.count('./.dev-data:/app/data') == 2
    assert 'studio-dev-db:/var/lib/postgresql/data' in dev
    assert '${DEV_HTTP_PORT:-8767}' in dev and 'ports: !override' in dev
    assert 'DATABASE_URL: ""' in dev
    assert 'PGPASSWORD: ${DEV_POSTGRES_PASSWORD:-studio-dev}' in dev
    assert dev.count('env_file: !override') == 2
    assert './realcenter-marketing-ai/.env' not in dev


@pytest.fixture(autouse=True)
def clean_database_environment(monkeypatch):
    for name in ('REALCENTER_DEPLOYMENT_MODE', 'DATABASE_URL', 'PGHOST', 'PGPORT',
                 'PGDATABASE', 'PGUSER', 'PGPASSWORD'):
        monkeypatch.delenv(name, raising=False)


def test_local_auto_mode_keeps_standalone_compatibility():
    assert database_url() is None


def test_explicit_database_keeps_existing_connections(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://existing/db')
    assert database_url() == 'postgresql://existing/db'
    monkeypatch.setenv('REALCENTER_DEPLOYMENT_MODE', 'shared')
    assert database_url() == 'postgresql://existing/db'


def test_shared_mode_never_falls_back_to_no_authentication(monkeypatch):
    monkeypatch.setenv('REALCENTER_DEPLOYMENT_MODE', 'shared')
    with pytest.raises(ValueError, match='Modo compartilhado exige'):
        database_url()


def test_compose_connection_preserves_special_characters(monkeypatch):
    monkeypatch.setenv('REALCENTER_DEPLOYMENT_MODE', 'shared')
    values = {'PGHOST': 'db', 'PGPORT': '5432', 'PGDATABASE': 'studio',
              'PGUSER': 'studio', 'PGPASSWORD': "test-only@:/#'\\ with spaces"}
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    connection = conninfo_to_dict(database_url())
    assert connection['host'] == 'db'
    assert connection['port'] == '5432'
    assert connection['dbname'] == connection['user'] == 'studio'
    assert connection['password'] == values['PGPASSWORD']


def test_disabling_authentication_requires_explicit_standalone_mode(monkeypatch):
    monkeypatch.setenv('REALCENTER_DEPLOYMENT_MODE', 'standalone')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://existing/db')
    assert database_url() is None


def test_misspelled_mode_fails_instead_of_disabling_authentication(monkeypatch):
    monkeypatch.setenv('REALCENTER_DEPLOYMENT_MODE', 'shraed')
    with pytest.raises(ValueError, match='REALCENTER_DEPLOYMENT_MODE'):
        database_url()


# ---- backup ------------------------------------------------------------------

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


# ---- data_layout -------------------------------------------------------------

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


# ---- data_migration ----------------------------------------------------------

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
