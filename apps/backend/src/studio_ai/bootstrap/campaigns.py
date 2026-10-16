"""Composition entry point shared by CLI, HTTP and offline evaluations."""
from studio_ai.application.campaigns.create_campaign import create_campaign as compose_campaign
from studio_ai.infrastructure.agents_sdk.runtime import execute_campaign
from studio_ai.infrastructure.persistence.filesystem import save_campaign
from studio_ai.infrastructure.resources import load_profile

async def create_campaign(brief, settings, *, model=None, option=None, journal=None):
    async def runtime(value):
        return await execute_campaign(value, settings, model=model, option=option, journal=journal)
    profile = load_profile(settings.project_root)
    return await compose_campaign(brief, runtime, demo=model is not None, journal=journal,
                                  deliverables=profile.deliverables)
