from studio_ai.application.integrations import SGSistemasPort
"""SG Sistemas boundary, pending the supplier's authentication/OpenAPI contract.

Paths were provided by the customer. Payloads, pagination and response fields
are intentionally unspecified. Importing this module performs no I/O.
"""
from typing import Any, Protocol

PREFIX = '/integracao/sgsistemas/v1'
ROUTES = (
    ('POST', PREFIX + '/autorizacao'),
    ('GET', PREFIX + '/produtos'),
    ('GET', PREFIX + '/filiais'),
    ('GET', PREFIX + '/ofertas'),
    ('GET', PREFIX + '/ofertas/produtos'),
    ('POST', PREFIX + '/ofertas/produtos'),
)




class SGSistemasAdapter:
    """Explicitly disabled until payload/authentication contracts are supplied."""
    async def _pending(self, *args, **kwargs):
        raise NotImplementedError('SG Sistemas aguarda contrato de autenticação e dados')

    authorize = products = branches = offers = offer_products = save_offer_products = _pending
