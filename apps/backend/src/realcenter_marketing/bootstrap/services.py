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
from .model_catalog import resolve_image, resolve_text
from .settings import Settings
from .paths import AppPaths


def CampaignService(root):
    """Build an isolated application service for the configured data root."""
    paths = AppPaths.discover(root)
    repository = FileCampaignRepository(paths.data_root)

    async def execute(brief, mode, journal, model_id=None):
        settings = Settings.load(paths.data_root)
        model = DemoModel(paths.demo_responses) if mode == 'demo' else None
        option = None if model else resolve_text(settings, model_id)
        return await create_campaign(brief, settings, model=model, option=option, journal=journal)

    async def assist(request, journal):
        return await improve_brief(request, Settings.load(paths.data_root), journal)

    def generate(campaign, journal, product, model_id=None, **options):
        settings = Settings.load(paths.data_root)
        option = resolve_image(settings, model_id)
        return generate_feed(campaign, settings, journal.directory, product, image_option=option,
                             on_response=lambda size, usage: journal.record_image_usage(option.model, size=size, usage=usage),
                             **options)

    def validate(request=None):
        """Each selected model answers for its own key; OpenAI keeps the original check."""
        settings = Settings.load(paths.data_root)
        chosen = []
        if request is not None:
            if getattr(request, 'mode', 'live') == 'live' and hasattr(request, 'model_id'):
                chosen.append(resolve_text(settings, request.model_id))
            if getattr(request, 'generate_image', True):
                chosen.append(resolve_image(settings, getattr(request, 'image_model_id', None)))
        if any(option is None for option in chosen):
            raise ValueError('O modelo selecionado não está disponível neste servidor')
        text = chosen[0] if chosen and getattr(request, 'mode', 'live') == 'live'             and hasattr(request, 'model_id') else None
        if text is not None and not text.delegates:
            raise ValueError(
                f'{text.label} não delega para os especialistas: o provedor desativa as '
                'ferramentas quando a entrega é estruturada, e o Director encerraria sem '
                'a campanha. Escolha um modelo OpenAI para a equipe.')
        external = [option for option in chosen if option.provider != 'openai']
        if len(external) < len(chosen) or not chosen:
            settings.validate_live()
        settings.validate_provider(*external)

    return ApplicationService(repository, LocalExecutionScheduler(), execute, assist,
                              ImageWorkflow(repository, generate), validate)
