"""Nemotron selection and the real SDK's Chat Completions wire contract (offline)."""
import asyncio
import json

try:
    import httpx2 as httpx
except ImportError:  # OpenAI SDK versions before the httpx2 migration.
    import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import SecretStr

from realcenter_marketing.application.commands import AssistRequest, RunRequest
from realcenter_marketing.bootstrap.campaigns import create_campaign
from realcenter_marketing.bootstrap.model_catalog import resolve_text, text_models
from realcenter_marketing.bootstrap.services import CampaignService
from realcenter_marketing.domain.campaigns import CampaignBrief
from realcenter_marketing.infrastructure.agents_sdk import runtime


MODEL = 'nvidia/nemotron-3-ultra-550b-a55b'
MODEL_ID = 'nvidia:' + MODEL


def test_brief_assistant_uses_selected_nemotron_without_openai(settings, monkeypatch):
    from realcenter_marketing.application.commands import AssistRequest
    from realcenter_marketing.bootstrap.settings import Settings
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
