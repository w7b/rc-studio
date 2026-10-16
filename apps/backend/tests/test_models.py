"""Catálogo de modelos, provedores, credenciais e contrato de fio."""
import asyncio
import base64
import io
import json
import pytest
from agents import ModelProvider
from pydantic import SecretStr
from PIL import Image
from studio_ai.bootstrap import model_catalog
from studio_ai.bootstrap.campaigns import create_campaign
from studio_ai.bootstrap.model_catalog import (
    KIMI_K3, NEMOTRON_ULTRA, QWEN_IMAGE, QWEN_TEXT, Z_IMAGE, Z_IMAGE_TURBO,
    Z_IMAGE_TURBO_LOCAL, display_name,
    image_models, qwen_canvas, resolve_image, resolve_text, text_models, zimage_canvas,
)
from studio_ai.bootstrap.settings import Settings
from studio_ai.domain.campaigns import CampaignBrief
from studio_ai.infrastructure import image_backends
try:
    import httpx2 as httpx
except ImportError:  # OpenAI SDK versions before the httpx2 migration.
    import httpx
from openai import AsyncOpenAI
from studio_ai.application.commands import AssistRequest, RunRequest
from studio_ai.bootstrap.model_catalog import resolve_text, text_models
from studio_ai.bootstrap.services import CampaignService
from studio_ai.infrastructure.agents_sdk import runtime
from studio_ai.infrastructure import model_credentials as keys


# ---- model_catalog -----------------------------------------------------------

def test_catalog_offers_both_providers_and_keeps_openai_default(settings):
    settings.model = 'fixture-model'
    assert [option.id for option in text_models(settings)] == [
        'openai:fixture-model', NEMOTRON_ULTRA.id, KIMI_K3.id, QWEN_TEXT.id]
    assert [option.id for option in image_models(settings)] == [
        'openai:gpt-image-2', Z_IMAGE_TURBO.id, Z_IMAGE.id, Z_IMAGE_TURBO_LOCAL.id, QWEN_IMAGE.id]
    # No explicit choice keeps the previous behaviour, never a silent switch of provider.
    assert resolve_text(settings, None).model == 'fixture-model'
    assert resolve_image(settings, None).model == 'gpt-image-2'
    assert resolve_text(settings, KIMI_K3.id).model == 'moonshotai/kimi-k3'
    assert resolve_text(settings, 'nvidia:inventado') is None


def test_unconfigured_env_still_defaults_to_openai(settings):
    settings.model = ''
    assert resolve_text(settings, None).provider == 'openai'
    with pytest.raises(ValueError, match='OPENAI_API_KEY'):
        settings.validate_live()


def test_each_provider_answers_for_its_own_key(settings):
    settings.api_key = SecretStr('')
    settings.nvidia_api_key = SecretStr('nvapi-fixture')
    settings.validate_provider(KIMI_K3, NEMOTRON_ULTRA)
    settings.nvidia_api_key = SecretStr('')
    with pytest.raises(ValueError, match='NVIDIA_API_KEY'):
        settings.validate_provider(KIMI_K3)
    # Z-Image goes through the Hugging Face router and answers for HF_TOKEN alone.
    with pytest.raises(ValueError, match='HF_TOKEN'):
        settings.validate_provider(Z_IMAGE_TURBO)
    settings.keys = {**settings.keys, 'huggingface': SecretStr('hf_fixture')}
    settings.validate_provider(Z_IMAGE_TURBO, Z_IMAGE)


def test_kimi_reaches_every_specialist_through_the_nvidia_endpoint(settings, demo, monkeypatch):
    from studio_ai.infrastructure.agents_sdk import runtime as workflow
    seen_models, seen_provider = [], {}

    class OfflineProvider(ModelProvider):
        def get_model(self, model_name):
            seen_models.append(model_name)
            return demo

    def provider_factory(*, openai_client, use_responses=None):
        seen_provider.update(api_key=openai_client.api_key,
                             base_url=str(openai_client.base_url).rstrip('/'),
                             use_responses=use_responses)
        return OfflineProvider()

    monkeypatch.setattr(workflow, 'OpenAIProvider', provider_factory)
    settings.nvidia_api_key = SecretStr('nvapi-fixture')
    settings.model = 'fixture-model'
    result = asyncio.run(create_campaign(CampaignBrief(request='Campanha'), settings, option=KIMI_K3))
    assert result.execution_mode == 'live'
    assert set(seen_models) == {'moonshotai/kimi-k3'} and len(seen_models) == 5
    assert seen_provider == {'api_key': 'nvapi-fixture',
                             'base_url': model_catalog.NVIDIA_TEXT_URL,
                             'use_responses': False}


# The native working canvas and the export of every publication preset, as
# image_generation pairs them.
PRESETS = {
    'feed_portrait': ('1152x1440', 1080, 1350), 'feed_square': ('1088x1088', 1080, 1080),
    'feed_landscape': ('1536x800', 1080, 566), 'feed_tall': ('1152x1536', 1080, 1440),
    'story': ('1152x2048', 1080, 1920), 'reel_cover': ('1152x2048', 1080, 1920),
}


def test_zimage_covers_every_publication_format():
    """Z-Image draws any aspect ratio inside a pixel-area band, so unlike the fixed-grid
    models it takes the 4:5 feed and the landscape as they stand, without upscaling."""
    for preset, (native, width, height) in PRESETS.items():
        assert zimage_canvas(native, width, height) == tuple(map(int, native.split('x'))), preset
        backend = image_backends.backend_for(Z_IMAGE_TURBO, api_key='hf_k', base_url='https://x')
        assert backend.canvas(native, width, height) == native, preset
    # Outside the band, or smaller than the export, is refused rather than bent.
    assert zimage_canvas('256x256', 256, 256) is None
    assert zimage_canvas('3000x3000', 1080, 1080) is None
    assert zimage_canvas('1000x1000', 1080, 1080) is None
    with pytest.raises(image_backends.ImageBackendError, match='área'):
        image_backends.backend_for(Z_IMAGE, api_key='hf_k', base_url='https://x').canvas(
            '3000x3000', 1080, 1080)


def test_qwen_image_covers_its_fixed_grid_but_not_the_45_feed():
    """Pinned to the seven resolutions the Qwen-Image-2.1 card documents.

    It reaches the square, the 3:4 and the story, but it has no 4:5 and no 1536x800,
    so those are refused instead of upscaled from a smaller frame.
    """
    assert qwen_canvas(1080, 1080) == (2048, 2048)
    assert qwen_canvas(1152, 1536) == (1792, 2400)
    assert qwen_canvas(1080, 1920) == (1536, 2752)
    assert qwen_canvas(1080, 1350) is None
    assert qwen_canvas(1536, 800) is None
    qwen = image_backends.backend_for(QWEN_IMAGE, api_key='k', base_url='http://x')
    assert qwen.canvas('1088x1088', 1080, 1080) == '2048x2048'
    with pytest.raises(image_backends.ImageBackendError, match='feed alto'):
        qwen.canvas('1152x1440', 1080, 1350)


def test_qwen_image_without_an_endpoint_refuses_instead_of_routing_elsewhere():
    """No Inference Provider serves this model, so an unset QWEN_IMAGE_URL is fatal and
    must say so — never fall through to another provider's endpoint."""
    qwen = image_backends.backend_for(QWEN_IMAGE, api_key='', base_url='')
    with pytest.raises(image_backends.ImageBackendError, match='QWEN_IMAGE_URL'):
        qwen.render('arte', '2048x2048', [])


def test_qwen_text_is_pinned_to_a_provider_that_honours_strict_schema(settings, demo):
    """Both halves of this id were measured against the live gateway.

    Novita wraps the answer in a JSON array on every setting tried, which fails strict
    validation; DeepInfra returns the object. And Qwen ships thinking on at xhigh, which
    spent the entire completion budget and returned empty content, so every agent in the
    team must carry the switch that turns it off.
    """
    from studio_ai.infrastructure.agents_sdk.team_factory import build_team

    assert QWEN_TEXT.model.endswith(':deepinfra'), 'o provedor de inferência é fixado de propósito'
    assert QWEN_TEXT.extra_body == {'chat_template_kwargs': {'enable_thinking': False}}
    team = build_team(settings, model=demo, option=QWEN_TEXT)
    for agent in (team.planner, team.reviewer, *team.specialists.values()):
        assert agent.model_settings.extra_body == QWEN_TEXT.extra_body


def test_an_unknown_provider_is_refused_rather_than_sent_to_openai():
    from studio_ai.bootstrap.model_catalog import ModelOption
    invented = ModelOption('outro:modelo', 'Outro', 'outro', 'modelo')
    with pytest.raises(image_backends.ImageBackendError, match='renderizador'):
        image_backends.backend_for(invented)


class FalFake:
    """The Hugging Face router in front of fal, then fal's media host.

    Records every request so a test can check what reached which host.
    """

    MEDIA = 'https://v3.fal.media/files/arte.jpg'

    def __init__(self, body=None, status=200):
        self.sent = []
        self.status = status
        jpeg = io.BytesIO()
        Image.new('RGB', (1152, 1440), 'orange').save(jpeg, 'JPEG')
        self.image = jpeg.getvalue()
        self.body = body if body is not None else {'images': [{'url': self.MEDIA}], 'seed': 7}

    def __call__(self, request, timeout=None):
        headers = {key.lower(): value for key, value in request.header_items()}
        self.sent.append({'url': request.full_url, 'method': request.get_method(),
                          'headers': headers, 'timeout': timeout,
                          'body': json.loads(request.data) if request.data else None})
        if request.full_url.startswith('https://router.huggingface.co/'):
            if self.status != 200:
                raise image_backends.urllib.error.HTTPError(
                    request.full_url, self.status, 'erro', {}, io.BytesIO(b'{"error": "fixture"}'))
            return _Answer(json.dumps(self.body).encode())
        return _Answer(self.image)


class _Answer:
    def __init__(self, content):
        self.content = content

    def read(self, limit=None):
        return self.content

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def zimage(option=Z_IMAGE_TURBO, key='hf_fixture'):
    return image_backends.backend_for(option, api_key=key,
                                      base_url=model_catalog.HUGGINGFACE_FAL_URL, timeout=60)


def test_zimage_speaks_the_fal_contract_and_returns_png(monkeypatch):
    """The contract of the official huggingface_hub client for fal: prompt plus
    image_size as {width, height}, then the pixels fetched from images[0].url."""
    fake = FalFake()
    monkeypatch.setattr(image_backends.urllib.request, 'urlopen', fake)
    content, usage = zimage().render('arte', '1152x1440', [])

    call, download = fake.sent
    assert call['url'] == 'https://router.huggingface.co/fal-ai/fal-ai/z-image/turbo'
    assert call['method'] == 'POST'
    assert call['headers']['authorization'] == 'Bearer hf_fixture'
    assert call['body'] == {'prompt': 'arte', 'image_size': {'width': 1152, 'height': 1440},
                            'num_inference_steps': 9, 'guidance_scale': 0.0}
    assert download['url'] == FalFake.MEDIA
    assert content.startswith(bytes([0x89]) + b'PNG'), 'o estúdio grava PNG em todo lugar'
    assert usage['model'] == 'fal-ai/z-image/turbo' and usage['seed'] == 7


def test_zimage_base_uses_the_sampling_its_card_specifies(monkeypatch):
    fake = FalFake()
    monkeypatch.setattr(image_backends.urllib.request, 'urlopen', fake)
    zimage(Z_IMAGE).render('arte', '1088x1088', [])
    assert fake.sent[0]['url'].endswith('/fal-ai/z-image/base')
    assert fake.sent[0]['body']['num_inference_steps'] == 30
    assert fake.sent[0]['body']['guidance_scale'] == 4.0


def test_zimage_never_hands_the_token_to_the_media_host(monkeypatch):
    """The media URL is public. Sending the Hugging Face token to a second host would
    give it away to whoever runs that host."""
    fake = FalFake()
    monkeypatch.setattr(image_backends.urllib.request, 'urlopen', fake)
    zimage().render('arte', '1152x1440', [])
    assert 'authorization' not in fake.sent[1]['headers']


def test_zimage_refusals_say_what_went_wrong(monkeypatch):
    with pytest.raises(image_backends.ImageBackendError, match='HF_TOKEN'):
        zimage(key='').render('arte', '1152x1440', [])

    monkeypatch.setattr(image_backends.urllib.request, 'urlopen', FalFake(status=402))
    with pytest.raises(image_backends.ImageBackendError, match='créditos'):
        zimage().render('arte', '1152x1440', [])

    # A flagged image still arrives as a file; saving it would publish a blank art.
    flagged = FalFake(body={'images': [{'url': FalFake.MEDIA}], 'has_nsfw_concepts': [True]})
    monkeypatch.setattr(image_backends.urllib.request, 'urlopen', flagged)
    with pytest.raises(image_backends.ImageBackendError, match='filtro de conteúdo'):
        zimage().render('arte', '1152x1440', [])
    assert len(flagged.sent) == 1, 'nada é baixado depois do bloqueio'

    monkeypatch.setattr(image_backends.urllib.request, 'urlopen', FalFake(body={'images': []}))
    with pytest.raises(image_backends.ImageBackendError, match='não retornou'):
        zimage().render('arte', '1152x1440', [])

    insecure = FalFake(body={'images': [{'url': 'http://v3.fal.media/files/arte.jpg'}]})
    monkeypatch.setattr(image_backends.urllib.request, 'urlopen', insecure)
    with pytest.raises(image_backends.ImageBackendError, match='endereço'):
        zimage().render('arte', '1152x1440', [])


def test_zimage_never_receives_brand_references():
    # Text-to-image only; describing a product photo it never saw would fake the art.
    for option in (Z_IMAGE_TURBO, Z_IMAGE):
        assert option.accepts_references is False and option.max_references == 0
        # Its text encoder stops at 512 tokens and truncates silently.
        assert option.max_prompt_chars <= 1_500
    assert resolve_image(Settings(project_root='.'), None).accepts_references is True


def test_labels_are_model_names_and_ids_stay_as_they_were(settings):
    """Saved campaigns and drafts store ids, so renaming must never touch them. The
    provider leaves the label and is exposed on its own, for the form to group by."""
    settings.model, settings.image_model = 'gpt-6-luna', 'gpt-image-2'
    texto = {option.id: option.label for option in text_models(settings)}
    assert texto == {
        'openai:gpt-6-luna': 'GPT-6 Luna',
        'nvidia:nvidia/nemotron-3-ultra-550b-a55b': 'NVIDIA Nemotron 3 Ultra',
        'nvidia:moonshotai/kimi-k3': 'Kimi K3',
        'huggingface:Qwen/Qwen3.8-27B:deepinfra': 'Qwen3.8 27B',
    }
    imagem = {option.id: option.label for option in image_models(settings)}
    assert imagem == {
        'openai:gpt-image-2': 'GPT Image 2',
        'huggingface:Tongyi-MAI/Z-Image-Turbo': 'Z-Image Turbo',
        'huggingface:Tongyi-MAI/Z-Image': 'Z-Image',
        'local:Tongyi-MAI/Z-Image-Turbo': 'Z-Image Turbo',
        'qwen:Qwen/Qwen-Image-2.1': 'Qwen-Image 2.1',
    }
    # Two options share a label on purpose; the provider group tells them apart.
    assert Z_IMAGE_TURBO_LOCAL.public(True)['provider_label'] == 'Na sua máquina'
    assert Z_IMAGE_TURBO.public(True)['provider_label'] == 'Hugging Face'
    assert not any('·' in label for label in (*texto.values(), *imagem.values()))
    assert display_name('gpt-5.6-sol') == 'GPT-5.6 Sol'
    assert display_name('modelo-desconhecido') == 'modelo-desconhecido'


def test_every_run_gets_its_own_connection_pool(settings):
    """The SDK shares one httpx client process-wide, and each run owns its event loop.

    A pooled connection outliving the loop that opened it raises
    RuntimeError('Event loop is closed') when the pool later closes it.
    """
    from agents.models import openai_provider as sdk
    from studio_ai.infrastructure.agents_sdk.runtime import build_provider, close_provider

    settings.api_key = SecretStr('sk-fixture')
    settings.nvidia_api_key = SecretStr('nvapi-fixture')
    first, second = build_provider(settings), build_provider(settings)
    assert first._get_client() is not second._get_client(), 'cada execução precisa do seu cliente'
    assert first._get_client()._client is not sdk.shared_http_client(), 'não pode ser o pool global'
    assert second._get_client()._client is not first._get_client()._client

    nvidia = build_provider(settings, KIMI_K3)
    assert str(nvidia._get_client().base_url).startswith(model_catalog.NVIDIA_TEXT_URL)
    assert nvidia._use_responses is False
    for provider in (first, second, nvidia):
        asyncio.run(close_provider(provider))


def test_a_model_that_cannot_delegate_is_now_accepted(tmp_path, monkeypatch):
    """The inverse of what this file used to assert, and the point of the pipeline.

    Kimi was refused because build.nvidia.com drops every tool call once the answer is
    constrained to a schema. No agent is given a tool any more, so that trade never
    happens and the model is free to direct a campaign.
    """
    from studio_ai.application.commands import RunRequest
    from studio_ai.bootstrap.services import CampaignService

    monkeypatch.setenv('OPENAI_API_KEY', 'sk-fixture')
    monkeypatch.setenv('OPENAI_MODEL', 'fixture-model')
    monkeypatch.setenv('NVIDIA_API_KEY', 'nvapi-fixture')
    service = CampaignService(tmp_path)
    assert not hasattr(KIMI_K3, 'delegates')
    service.validate_live(RunRequest(request='Campanha', model_id=KIMI_K3.id))
    service.validate_live(RunRequest(request='Campanha'))


# ---- nemotron ----------------------------------------------------------------

MODEL = 'nvidia/nemotron-3-ultra-550b-a55b'


MODEL_ID = 'nvidia:' + MODEL


def test_brief_assistant_uses_selected_nemotron_without_openai(settings, monkeypatch):
    from studio_ai.application.commands import AssistRequest
    from studio_ai.bootstrap.settings import Settings
    settings.nvidia_api_key = SecretStr('nvapi-fixture')
    settings.api_key = SecretStr('')
    settings.model = ''
    monkeypatch.setattr(Settings, 'load', lambda *args, **kwargs: settings)
    calls, clients = [], []
    suggestion = {'improved_request': 'Divulgue o produto no Feed.',
                  'changes': ['Objetivo mais claro.'], 'questions': ['Qual é o produto?']}

    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        assert str(request.url) == 'https://integrate.api.nvidia.com/v1/chat/completions'
        assert request.headers['Authorization'] == 'Bearer nvapi-fixture'
        assert body['model'] == MODEL
        assert body['response_format']['json_schema']['schema']['title'] == 'BriefSuggestion'
        return httpx.Response(200, json={'id': 'brief-nemotron', 'object': 'chat.completion',
            'created': 0, 'model': MODEL,
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': json.dumps(suggestion)},
                         'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}})

    def client_factory(**kwargs):
        client = AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
        clients.append(client)
        return client

    monkeypatch.setattr(runtime, 'AsyncOpenAI', client_factory)
    service = CampaignService(settings.project_root)
    try:
        result = service.assist(AssistRequest(request='Divulgar produto', model_id=MODEL_ID))
        assert result['suggestion'] == suggestion
        assert len(calls) == 1
        assert clients[0].is_closed()
        assert not service.busy
        settings.nvidia_api_key = SecretStr('')
        with pytest.raises(ValueError, match='NVIDIA_API_KEY'):
            service.assist(AssistRequest(request='Divulgar produto', model_id=MODEL_ID))
        assert len(calls) == 1
    finally:
        service.close(timeout=1)


def test_nemotron_selection_requires_only_its_provider_key(tmp_path, monkeypatch, settings):
    monkeypatch.setenv('OPENAI_API_KEY', '')
    monkeypatch.setenv('OPENAI_MODEL', '')
    monkeypatch.setenv('NVIDIA_API_KEY', 'nvapi-fixture')
    option = resolve_text(settings, MODEL_ID)
    assert option is not None
    assert option in text_models(settings)
    # A capability the catalog no longer has to advertise: with the pipeline driving the
    # specialists, nothing asks this model to call a tool, so it is offered as Director.
    assert 'delegates' not in option.public(True)
    service = CampaignService(tmp_path)
    request = RunRequest(request='Campanha', model_id=MODEL_ID, generate_image=False)
    service.validate_live(request)
    assist = AssistRequest(request='Campanha', model_id=MODEL_ID)
    service.validate_live(assist)
    monkeypatch.setenv('NVIDIA_API_KEY', '')
    with pytest.raises(ValueError, match='NVIDIA_API_KEY'):
        service.validate_live(assist)


def test_nemotron_runs_a_campaign_without_ever_being_sent_a_tool(settings, demo, monkeypatch):
    option = resolve_text(settings, MODEL_ID)
    assert option is not None
    settings.nvidia_api_key = SecretStr('nvapi-fixture')
    settings.api_key = SecretStr('')
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert str(request.url) == 'https://integrate.api.nvidia.com/v1/chat/completions'
        assert request.headers['Authorization'] == 'Bearer nvapi-fixture'
        assert body['model'] == MODEL
        assert body['response_format']['type'] == 'json_schema'
        # The wire contract this file exists to pin, now inverted: structured output
        # alone, never combined with tools. NVIDIA drops every tool call when both are
        # sent, and that is exactly the combination the pipeline stopped needing.
        assert not body.get('tools'), 'nenhuma requisicao pode carregar tools'
        schema_name = body['response_format']['json_schema']['schema']['title']
        message = {'role': 'assistant',
                   'content': json.dumps(demo.responses[schema_name], ensure_ascii=False)}
        return httpx.Response(200, json={'id': f'chat-{len(requests)}', 'object': 'chat.completion',
                                       'created': 0, 'model': MODEL,
                                       'choices': [{'index': 0, 'message': message, 'finish_reason': 'stop'}],
                                       'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}})

    clients = []

    def client_factory(**kwargs):
        client = AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
        clients.append(client)
        return client

    monkeypatch.setattr(runtime, 'AsyncOpenAI', client_factory)
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Campanha institucional'), settings, option=option))
    assert campaign.execution_mode == 'live'
    assert len(requests) == 5
    assert [r['response_format']['json_schema']['schema']['title'] for r in requests] == [
        'CampaignPlan', 'SocialPlan', 'CopyPack', 'CreativeBrief', 'DirectorReview',
    ]
    assert clients[0].is_closed()


# ---- settings ----------------------------------------------------------------

def test_timeout_accepts_twenty_minutes(tmp_path, monkeypatch):
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "1200")
    assert Settings.load(tmp_path).timeout_seconds == 1200


def test_env_loading_and_environment_precedence(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=fixture-secret\nOPENAI_MODEL=fixture-model\nMAX_TURNS=8\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MAX_TURNS", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "environment-model")
    settings = Settings.load(tmp_path)
    assert settings.model == "environment-model"
    assert settings.max_turns == 8
    assert settings.api_key.get_secret_value() == "fixture-secret"
    assert "fixture-secret" not in repr(settings)


def test_live_provider_is_inherited_by_all_specialists(settings, demo, monkeypatch):
    from studio_ai.infrastructure.agents_sdk import runtime as workflow
    seen_models = []

    class OfflineProvider(ModelProvider):
        def get_model(self, model_name):
            seen_models.append(model_name)
            return demo

    def provider_factory(*, openai_client, use_responses=None):
        # The runtime now builds the client itself, so each run owns its connection pool.
        assert openai_client.api_key == "fixture-secret"
        return OfflineProvider()

    monkeypatch.setattr(workflow, "OpenAIProvider", provider_factory)
    settings.api_key = SecretStr("fixture-secret")
    settings.model = "fixture-model"
    result = asyncio.run(create_campaign(CampaignBrief(request="Campanha"), settings))
    assert result.execution_mode == "live"
    # Plan, three specialists, review: one call each, no Director re-reads.
    assert len(seen_models) == 5
    assert set(seen_models) == {"fixture-model"}


# ---- model_credentials -------------------------------------------------------

def test_store_keys_are_isolated_and_override_inheritance_without_echoing(tmp_path, monkeypatch):
    platform, first, second = (tmp_path / name for name in ('platform', 'first', 'second'))
    platform.mkdir()
    monkeypatch.setenv('OPENAI_API_KEY', 'platform-test-key')
    keys.save(platform, first, {'openai': {'action': 'replace', 'key': 'store-test-key'}})
    assert Settings.load(first, env_root=platform).credential('openai') == 'store-test-key'
    assert Settings.load(second, env_root=platform).credential('openai') == 'platform-test-key'
    view = keys.public(platform, first, {'OPENAI_API_KEY': 'platform-test-key'})
    assert view['providers']['openai']['source'] == 'store'
    assert 'store-test-key' not in json.dumps(view)
    assert 'platform-test-key' not in json.dumps(view)
    assert not (first / '.model-keys').exists()
    keys.save(platform, first, {'openai': {'action': 'inherit'}})
    assert Settings.load(first, env_root=platform).credential('openai') == 'platform-test-key'


def test_tenant_files_cannot_override_platform_managed_credentials(tmp_path, monkeypatch):
    platform, tenant = tmp_path / 'platform', tmp_path / 'tenant'
    platform.mkdir()
    tenant.mkdir()
    monkeypatch.setenv('OPENAI_API_KEY', 'platform-test-key')
    (tenant / '.env').write_text('OPENAI_API_KEY=untrusted-key\nNVIDIA_BASE_URL=https://untrusted.test')
    keys.save(tenant, tenant, {'openai': {'action': 'replace', 'key': 'untrusted-key'}})
    settings = Settings.load(tenant, env_root=platform)
    assert settings.credential('openai') == 'platform-test-key'
    assert 'untrusted' not in settings.nvidia_base_url


@pytest.mark.parametrize('changes', [None, [], {}, {'unknown': {'action': 'replace', 'key': 'key'}},
    {'openai': {'action': 'replace', 'key': ''}}, {'openai': {'action': 'replace', 'key': 'bad\nkey'}},
    {'openai': {'action': 'unknown'}}, {'openai': {'action': 'replace', 'key': 12}}])
def test_invalid_key_edits_leave_existing_keys_intact(tmp_path, changes):
    tenant = tmp_path / 'tenant'
    keys.save(tmp_path, tenant, {'openai': {'action': 'replace', 'key': 'old-test-key'}})
    with pytest.raises(ValueError):
        keys.save(tmp_path, tenant, changes)
    assert keys.load(tmp_path, tenant)['openai'] == 'old-test-key'


def test_bad_storage_fails_instead_of_silently_billing_global_key(tmp_path):
    tenant = tmp_path / 'tenant'
    keys.save(tmp_path, tenant, {'openai': {'action': 'replace', 'key': 'test-key'}})
    next((tmp_path / '.model-keys').glob('*.json')).write_text('{bad json')
    with pytest.raises(ValueError, match='ler as chaves'):
        keys.load(tmp_path, tenant)


# ---- z-image local -----------------------------------------------------------

def test_a_self_hosted_model_is_available_once_its_address_is_set(settings):
    """For a server someone runs, the address is what is missing, not a key. Qwen-Image
    used to show "sem chave" with its endpoint configured, because only the key counted."""
    for option, env in ((Z_IMAGE_TURBO_LOCAL, 'local_image'), (QWEN_IMAGE, 'qwen_image')):
        settings.endpoints = {}
        assert not settings.has(option)
        with pytest.raises(ValueError, match='ligue o servidor'):
            settings.validate_provider(option)
        settings.endpoints = {env: 'http://host.docker.internal:8001/generate'}
        assert settings.has(option), 'sem chave nenhuma, só o endereço'
        settings.validate_provider(option)


class LocalFake:
    def __init__(self, body=None, status=200, refuse=False):
        png = io.BytesIO()
        Image.new('RGB', (1152, 1440), 'orange').save(png, 'PNG')
        self.body = body if body is not None else {
            'image': base64.b64encode(png.getvalue()).decode(), 'seed': 11, 'seconds': 42.0}
        self.status, self.refuse, self.sent = status, refuse, []

    def __call__(self, request, timeout=None):
        headers = {key.lower(): value for key, value in request.header_items()}
        self.sent.append({'url': request.full_url, 'headers': headers, 'timeout': timeout,
                          'body': json.loads(request.data)})
        if self.refuse:
            raise image_backends.urllib.error.URLError(ConnectionRefusedError(10061, 'recusada'))
        if self.status != 200:
            raise image_backends.urllib.error.HTTPError(
                request.full_url, self.status, 'erro', {}, io.BytesIO(b'{"error": "sem memoria"}'))
        return _Answer(json.dumps(self.body).encode())


def local(url='http://host.docker.internal:8001/generate', key='segredo'):
    return image_backends.backend_for(Z_IMAGE_TURBO_LOCAL, api_key=key, base_url=url, timeout=900)


def test_local_zimage_speaks_the_servers_contract(monkeypatch):
    fake = LocalFake()
    monkeypatch.setattr(image_backends.urllib.request, 'urlopen', fake)
    content, usage = local().render('arte', '1152x1440', [])
    call = fake.sent[0]
    assert call['url'] == 'http://host.docker.internal:8001/generate'
    assert call['headers']['authorization'] == 'Bearer segredo'
    assert call['body'] == {'prompt': 'arte', 'width': 1152, 'height': 1440,
                            'num_inference_steps': 9, 'guidance_scale': 0.0}
    assert call['timeout'] == 900, 'uma placa doméstica demora; o prazo é o do run'
    assert content.startswith(bytes([0x89]) + b'PNG')
    assert usage['provider'] == 'local' and usage['seed'] == 11 and usage['seconds'] == 42.0


def test_local_zimage_covers_every_publication_format():
    backend = local()
    for preset, (native, width, height) in PRESETS.items():
        assert backend.canvas(native, width, height) == native, preset


def test_local_zimage_refusals_say_what_to_do(monkeypatch):
    with pytest.raises(image_backends.ImageBackendError, match='LOCAL_IMAGE_URL'):
        local(url='').render('arte', '1152x1440', [])

    monkeypatch.setattr(image_backends.urllib.request, 'urlopen', LocalFake(refuse=True))
    with pytest.raises(image_backends.ImageBackendError, match='zimage_server.py'):
        local().render('arte', '1152x1440', [])

    monkeypatch.setattr(image_backends.urllib.request, 'urlopen', LocalFake(status=507))
    with pytest.raises(image_backends.ImageBackendError, match='sem memoria'):
        local().render('arte', '1152x1440', [])

    monkeypatch.setattr(image_backends.urllib.request, 'urlopen', LocalFake(body={}))
    with pytest.raises(image_backends.ImageBackendError, match='não retornou'):
        local().render('arte', '1152x1440', [])

    # Without a token the header is simply absent, never "Bearer " with nothing after it.
    fake = LocalFake()
    monkeypatch.setattr(image_backends.urllib.request, 'urlopen', fake)
    local(key='').render('arte', '1152x1440', [])
    assert 'authorization' not in fake.sent[0]['headers']


def test_the_local_server_validates_before_touching_the_gpu():
    """The request guard runs before torch is even imported, so it is testable here."""
    from script_loader import load_script
    server = load_script('zimage_server')
    prompt, width, height, steps, guidance, seed = server.validar(
        {'prompt': ' arte ', 'width': 1152, 'height': 1440, 'seed': 3})
    assert (prompt, width, height, steps, guidance, seed) == ('arte', 1152, 1440, 9, 0.0, 3)
    for ruim, motivo in (({'prompt': '', 'width': 1024, 'height': 1024}, 'vazio'),
                         ({'prompt': 'a', 'width': 1000, 'height': 1024}, 'múltiplos'),
                         ({'prompt': 'a', 'width': 4096, 'height': 4096}, 'faixa'),
                         ({'prompt': 'a', 'width': 1024, 'height': 1024,
                           'num_inference_steps': 500}, 'entre')):
        with pytest.raises(ValueError, match=motivo):
            server.validar(ruim)
