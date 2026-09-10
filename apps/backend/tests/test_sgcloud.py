import asyncio
from datetime import date

import pytest

from realcenter_marketing.infrastructure.integrations.sgcloud import MockSGCloudAdapter, Product, Sales, SGCloudAdapter, Stock


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
