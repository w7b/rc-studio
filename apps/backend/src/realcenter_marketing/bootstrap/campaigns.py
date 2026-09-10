"""Composition entry point shared by CLI, HTTP and offline evaluations."""
from realcenter_marketing.application.campaigns.create_campaign import create_campaign as compose_campaign
from realcenter_marketing.infrastructure.agents_sdk.runtime import execute_campaign
from realcenter_marketing.infrastructure.persistence.filesystem import save_campaign

async def create_campaign(brief, settings, *, model=None, journal=None):
    async def runtime(value):
        return await execute_campaign(value, settings, model=model, journal=journal)
    return await compose_campaign(brief, runtime, demo=model is not None, journal=journal)
