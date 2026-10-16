"""Integrações externas: SGCloud e Meta Ads."""
import asyncio
from datetime import date
import pytest
from studio_ai.infrastructure.integrations.sgcloud import MockSGCloudAdapter, Product, Sales, SGCloudAdapter, Stock
import io
import json
from urllib.error import HTTPError
from studio_ai.infrastructure import integrations_config
from studio_ai.infrastructure.integrations.meta_ads import validate_connection


# ---- sgcloud -----------------------------------------------------------------

def test_mock_returns_only_provided_read_only_data():
    product = Product(id="fixture-1", name="Produto fictício para teste", category="Fixture")
    adapter = MockSGCloudAdapter(products=[product], stocks=[Stock(product_id=product.id, quantity=4)])
    assert isinstance(adapter, SGCloudAdapter)
    result = asyncio.run(adapter.get_product(product.id))
    result.name = "Alterado localmente"
    assert asyncio.run(adapter.get_product(product.id)).name == product.name
    assert asyncio.run(adapter.get_stock(product.id)).quantity == 4
    assert asyncio.run(adapter.get_stock("unknown")) is None
    assert asyncio.run(adapter.get_product("unknown")) is None
    assert {m for m in dir(adapter) if not m.startswith("_")} == {"get_product", "get_stock", "get_sales"}
    with pytest.raises(ValueError):
        Product(id="1", name="Teste", category="Fixture", price=5)


def test_sales_requires_exact_fixture_period():
    start, end = date(2026, 9, 1), date(2026, 9, 8)
    sale = Sales(product_id="fixture-1", start=start, end=end, units=3)
    adapter = MockSGCloudAdapter(sales=[sale])
    assert asyncio.run(adapter.get_sales("fixture-1", start, end)) == sale
    assert asyncio.run(adapter.get_sales("missing", start, end)) is None
    assert asyncio.run(adapter.get_sales("fixture-1", start, start)) is None
    with pytest.raises(ValueError, match="Período"):
        asyncio.run(adapter.get_sales("fixture-1", end, start))


# ---- meta_ads_validation -----------------------------------------------------

SETTINGS = {'enabled': True, 'ad_account_id': 'act_123', 'api_version': 'v24.0', 'access_token': 'never-echo-me'}


def test_validation_checks_account_and_campaign_read_without_publishing():
    calls = []
    def get(version, path, token, params):
        calls.append(path)
        return {'data': []} if path.endswith('/campaigns') else {'id': 'act_123', 'account_status': 1, 'name': 'Loja'}
    result = validate_connection(SETTINGS, get)
    assert calls == ['act_123', 'act_123/campaigns']
    assert result['status'] == 'connected' and not result['publishing_available']
    assert 'never-echo-me' not in json.dumps(result)


def test_invalid_or_disabled_config_never_makes_a_network_request():
    def no_network(*args):
        raise AssertionError('network')
    assert validate_connection({}, no_network)['status'] == 'disabled'
    assert validate_connection({**SETTINGS, 'ad_account_id': '123/evil'}, no_network)['status'] == 'incomplete'
    assert validate_connection({**SETTINGS, 'api_version': ''}, no_network)['status'] == 'incomplete'


def test_invalid_token_is_reported_without_provider_details():
    def get(*args):
        raise HTTPError('url', 400, 'bad token', {}, io.BytesIO(b'{"error":{"code":190,"message":"never-echo-me"}}'))
    result = validate_connection(SETTINGS, get)
    assert result['status'] == 'error' and result['error_code'] == 190
    assert 'never-echo-me' not in json.dumps(result)


def test_settings_never_expose_secrets_and_edits_invalidate_diagnostics(tmp_path, monkeypatch):
    integrations_config.save(tmp_path, 'meta_ads', SETTINGS)
    monkeypatch.setattr('studio_ai.infrastructure.integrations.meta_ads.validate_connection',
                        lambda _: {'status': 'connected', 'publishing_available': False})
    integrations_config.validate_meta(tmp_path)
    assert integrations_config.public(tmp_path)['meta_ads']['validation']['status'] == 'connected'
    public = integrations_config.save(tmp_path, 'meta_ads', {**SETTINGS, 'access_token': ''})
    assert public['meta_ads']['validation'] is None
    assert public['meta_ads']['secrets']['access_token'] is True
    assert 'never-echo-me' not in json.dumps(public)
