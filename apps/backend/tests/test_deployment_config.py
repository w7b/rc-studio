import pytest
from pathlib import Path
from psycopg.conninfo import conninfo_to_dict

from realcenter_marketing.infrastructure.identity.database import database_url

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
