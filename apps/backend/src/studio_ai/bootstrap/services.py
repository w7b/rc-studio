"""Composition root for campaign commands. No process-global campaign state."""
from studio_ai.application.campaigns.service import CampaignService as ApplicationService
from studio_ai.application.commands import RunRequest, ImageRequest, AssistRequest
from studio_ai.application.errors import BusyError
from studio_ai.application.images import ImageWorkflow
from studio_ai.infrastructure.agents_sdk.demo import DemoModel
from studio_ai.infrastructure.agents_sdk.brief_assistant import improve_brief
from studio_ai.infrastructure.image_generation import generate_feed
from studio_ai.infrastructure.execution import LocalExecutionScheduler
from studio_ai.infrastructure.persistence.campaign_repository import FileCampaignRepository
from .campaigns import create_campaign
from .model_catalog import resolve_image, resolve_text
from studio_ai.application.consultations import ConsultationService
from studio_ai.infrastructure.agents_sdk.consultations import execute_consultation
from .settings import Settings
from .paths import AppPaths


def CampaignService(root, scheduler=None, quota=None, env_root=None, queue=None):
    """Build an isolated application service for the configured data root.

    A shared deployment passes a scheduler drawn from one pool, which is what makes the
    global ceiling apply across stores while each store keeps its own slot. Standalone
    gets a pool of its own with capacity one, exactly as before."""
    paths = AppPaths.discover(root)
    def settings_for_store():
        return Settings.load(paths.data_root, env_root=env_root or paths.env_root)
    repository = FileCampaignRepository(paths.data_root)

    async def execute(brief, mode, journal, model_id=None):
        settings = settings_for_store()
        model = DemoModel(paths.demo_responses) if mode == 'demo' else None
        option = None if model else resolve_text(settings, model_id)
        return await create_campaign(brief, settings, model=model, option=option, journal=journal)

    async def assist(request, journal):
        settings = settings_for_store()
        return await improve_brief(request, settings, journal,
                                   option=resolve_text(settings, request.model_id))

    def generate(campaign, journal, product, model_id=None, **options):
        settings = settings_for_store()
        option = resolve_image(settings, model_id)
        return generate_feed(campaign, settings, journal.directory, product, image_option=option,
                             on_response=lambda size, usage: journal.record_image_usage(option.model, size=size, usage=usage),
                             **options)

    def validate(request=None):
        """Each selected model answers for its own key; OpenAI keeps the original check."""
        settings = settings_for_store()
        chosen = []
        if request is not None:
            if getattr(request, 'mode', 'live') == 'live' and hasattr(request, 'model_id'):
                chosen.append(resolve_text(settings, request.model_id))
            if not isinstance(request, AssistRequest) and getattr(request, 'generate_image', True):
                chosen.append(resolve_image(settings, getattr(request, 'image_model_id', None)))
        if any(option is None for option in chosen):
            raise ValueError('O modelo selecionado não está disponível neste servidor')
        external = [option for option in chosen if option.provider != 'openai']
        if len(external) < len(chosen) or not chosen:
            settings.validate_live()
        settings.validate_provider(*external)

    scheduler = scheduler or LocalExecutionScheduler()
    service = ApplicationService(repository, scheduler, execute, assist,
                                 ImageWorkflow(repository, generate), validate, quota, queue)

    def validate_consultation(request):
        settings = settings_for_store()
        option = resolve_text(settings, request.model_id)
        if option is None:
            raise ValueError('O modelo selecionado não está disponível neste servidor')
        if option.provider == 'openai':
            settings.validate_live()
        else:
            settings.validate_provider(option)

    async def consult(request, journal):
        settings = settings_for_store()
        return await execute_consultation(request, settings, journal,
                                          option=resolve_text(settings, request.model_id))

    service.consultations = ConsultationService(repository, scheduler, consult,
                                               validate_consultation, quota, queue)
    return service
