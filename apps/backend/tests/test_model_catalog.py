"""Kimi K3 for the agents and FLUX.1 dev for a parallel art comparison."""
import asyncio
import base64
import io
import json

import pytest
from agents import ModelProvider
from pydantic import SecretStr
from PIL import Image

from realcenter_marketing.bootstrap import model_catalog
from realcenter_marketing.bootstrap.campaigns import create_campaign
from realcenter_marketing.bootstrap.model_catalog import (
    FLUX_DEV, KIMI_K3, NEMOTRON_ULTRA, QWEN_IMAGE, QWEN_TEXT, flux_canvas, image_models,
    qwen_canvas, resolve_image, resolve_text, text_models,
)
from realcenter_marketing.bootstrap.settings import Settings
from realcenter_marketing.domain.campaigns import CampaignBrief
from realcenter_marketing.infrastructure import image_backends


def test_catalog_offers_both_providers_and_keeps_openai_default(settings):
    settings.model = 'fixture-model'
    assert [option.id for option in text_models(settings)] == [
        'openai:fixture-model', NEMOTRON_ULTRA.id, KIMI_K3.id, QWEN_TEXT.id]
    assert [option.id for option in image_models(settings)] == [
        'openai:gpt-image-2', FLUX_DEV.id, QWEN_IMAGE.id]
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
    settings.validate_provider(KIMI_K3, FLUX_DEV)
    settings.nvidia_api_key = SecretStr('')
    with pytest.raises(ValueError, match='NVIDIA_API_KEY'):
        settings.validate_provider(KIMI_K3)


def test_kimi_reaches_every_specialist_through_the_nvidia_endpoint(settings, demo, monkeypatch):
    from realcenter_marketing.infrastructure.agents_sdk import runtime as workflow
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


def test_flux_only_covers_the_square_export():
    # 1344 px is the tallest side FLUX draws; taller exports would need upscaling.
    assert flux_canvas(1080, 1080) == (1088, 1088)
    assert flux_canvas(1080, 1350) is None
    assert flux_canvas(1080, 1920) is None
    flux = image_backends.backend_for(FLUX_DEV, api_key='k', base_url='http://x')
    assert flux.canvas('1088x1088', 1080, 1080) == '1088x1088'
    with pytest.raises(image_backends.ImageBackendError, match='1344'):
        flux.canvas('1152x2048', 1080, 1920)


def test_qwen_image_covers_more_exports_than_flux_but_not_the_45_feed():
    """Pinned to the seven resolutions the Qwen-Image-2.1 card documents.

    It reaches the square, the 3:4 and the story, which FLUX cannot, but it has no 4:5
    and no 1536x800, so those are refused instead of upscaled from a smaller frame.
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
    from realcenter_marketing.infrastructure.agents_sdk.team_factory import build_team

    assert QWEN_TEXT.model.endswith(':deepinfra'), 'o provedor de inferência é fixado de propósito'
    assert QWEN_TEXT.extra_body == {'chat_template_kwargs': {'enable_thinking': False}}
    team = build_team(settings, model=demo, option=QWEN_TEXT)
    for agent in (team.planner, team.reviewer, *team.specialists.values()):
        assert agent.model_settings.extra_body == QWEN_TEXT.extra_body


def test_an_unknown_provider_is_refused_rather_than_sent_to_openai():
    from realcenter_marketing.bootstrap.model_catalog import ModelOption
    invented = ModelOption('outro:modelo', 'Outro', 'outro', 'modelo')
    with pytest.raises(image_backends.ImageBackendError, match='renderizador'):
        image_backends.backend_for(invented)


def test_flux_sends_a_valid_request_and_returns_png(settings, monkeypatch):
    settings.nvidia_api_key = SecretStr('nvapi-fixture')
    jpeg = io.BytesIO()
    Image.new('RGB', (1088, 1088), 'orange').save(jpeg, 'JPEG')
    sent = {}

    class Response:
        def read(self):
            return json.dumps({'artifacts': [{'base64': base64.b64encode(jpeg.getvalue()).decode(),
                                              'seed': 7, 'finishReason': 'SUCCESS'}]}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        sent.update(url=request.full_url, body=json.loads(request.data),
                    auth=request.headers.get('Authorization'), timeout=timeout)
        return Response()

    monkeypatch.setattr(image_backends.urllib.request, 'urlopen', fake_urlopen)
    flux = image_backends.backend_for(FLUX_DEV, api_key=settings.credential('nvidia'),
                                      base_url=settings.nvidia_image_url, timeout=60)
    content, usage = flux.render('arte', '1088x1088', [])
    assert sent['url'] == model_catalog.NVIDIA_IMAGE_URL + '/black-forest-labs/flux.1-dev'
    assert sent['auth'] == 'Bearer nvapi-fixture'
    assert sent['body']['width'] == sent['body']['height'] == 1088
    assert sent['body']['steps'] >= 5, 'FLUX recusa menos de 5 passos'
    assert content.startswith(bytes([0x89]) + b'PNG'), 'o estúdio grava PNG em todo lugar'
    assert usage['model'] == 'black-forest-labs/flux.1-dev'
    assert usage['seed'] == 7


def test_flux_never_receives_brand_references():
    # It is text-to-image only; sending references silently would fake the comparison.
    assert FLUX_DEV.accepts_references is False and FLUX_DEV.max_references == 0
    assert resolve_image(Settings(project_root='.'), None).accepts_references is True


def test_every_run_gets_its_own_connection_pool(settings):
    """The SDK shares one httpx client process-wide, and each run owns its event loop.

    A pooled connection outliving the loop that opened it raises
    RuntimeError('Event loop is closed') when the pool later closes it.
    """
    from agents.models import openai_provider as sdk
    from realcenter_marketing.infrastructure.agents_sdk.runtime import build_provider, close_provider

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
    from realcenter_marketing.application.commands import RunRequest
    from realcenter_marketing.bootstrap.services import CampaignService

    monkeypatch.setenv('OPENAI_API_KEY', 'sk-fixture')
    monkeypatch.setenv('OPENAI_MODEL', 'fixture-model')
    monkeypatch.setenv('NVIDIA_API_KEY', 'nvapi-fixture')
    service = CampaignService(tmp_path)
    assert not hasattr(KIMI_K3, 'delegates')
    service.validate_live(RunRequest(request='Campanha', model_id=KIMI_K3.id))
    service.validate_live(RunRequest(request='Campanha'))
