from realcenter_marketing.domain.marketing import Product, Stock, Sales
from realcenter_marketing.application.integrations import SGCloudAdapter
from datetime import date

class MockSGCloudAdapter:
    """Fixtures explícitas em memória. Nunca instancia cliente HTTP."""

    def __init__(self, products=(), stocks=(), sales=()):
        self._products = {p.id: p.model_copy(deep=True) for p in products}
        self._stocks = {s.product_id: s.model_copy(deep=True) for s in stocks}
        self._sales = {(s.product_id, s.start, s.end): s.model_copy(deep=True) for s in sales}

    @staticmethod
    def _copy(value):
        return value.model_copy(deep=True) if value is not None else None

    async def get_product(self, product_id: str) -> Product | None:
        return self._copy(self._products.get(product_id))

    async def get_stock(self, product_id: str) -> Stock | None:
        return self._copy(self._stocks.get(product_id))

    async def get_sales(self, product_id: str, start: date, end: date) -> Sales | None:
        if start > end:
            raise ValueError("Período de vendas inválido")
        return self._copy(self._sales.get((product_id, start, end)))
