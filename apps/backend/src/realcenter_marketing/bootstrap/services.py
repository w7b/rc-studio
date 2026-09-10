"""Composition root for campaign commands. No process-global campaign state."""
from realcenter_marketing.application.campaigns.service import CampaignService as ApplicationService
from realcenter_marketing.application.commands import RunRequest, ImageRequest
from realcenter_marketing.application.errors import BusyError
from realcenter_marketing.application.images import ImageWorkflow
from realcenter_marketing.infrastructure.agents_sdk.demo import DemoModel
from realcenter_marketing.infrastructure.agents_sdk.brief_assistant import improve_brief
from realcenter_marketing.infrastructure.image_generation import generate_feed
from realcenter_marketing.infrastructure.execution import LocalExecutionScheduler
from realcenter_marketing.infrastructure.persistence.campaign_repository import FileCampaignRepository
from .campaigns import create_campaign
from .settings import Settings
from .paths import AppPaths


def CampaignService(root):
    """Build an isolated application service for the configured data root."""
    paths = AppPaths.discover(root)
    repository = FileCampaignRepository(paths.data_root)

    async def execute(brief, mode, journal):
        settings = Settings.load(paths.data_root)
        model = DemoModel(paths.demo_responses) if mode == 'demo' else None
        return await create_campaign(brief, settings, model=model, journal=journal)

    async def assist(request, journal):
        return await improve_brief(request, Settings.load(paths.data_root), journal)

    def generate(campaign, journal, product, **options):
        settings = Settings.load(paths.data_root)
        return generate_feed(campaign, settings, journal.directory, product,
                             on_response=lambda size, usage: journal.record_image_usage(settings.image_model, size=size, usage=usage),
                             **options)

    return ApplicationService(repository, LocalExecutionScheduler(), execute, assist,
                              ImageWorkflow(repository, generate),
                              lambda: Settings.load(paths.data_root).validate_live())
