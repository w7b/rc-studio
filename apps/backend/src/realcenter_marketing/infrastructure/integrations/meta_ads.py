from realcenter_marketing.application.integrations import MetaAdsPort
"""Inactive port for the future Ads module; no credentials, SDK or writes."""
from typing import Any, Protocol




class MetaAdsAdapter:
    async def _pending(self, *args, **kwargs):
        raise NotImplementedError('Meta Ads aguarda autenticação, conta, permissões e versão da API')

    account = campaigns = insights = create_draft = _pending
