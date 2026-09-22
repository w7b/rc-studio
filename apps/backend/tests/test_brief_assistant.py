import asyncio
import json

import pytest

from realcenter_marketing.infrastructure.observability.journal import RunJournal
from realcenter_marketing.infrastructure.agents_sdk.brief_assistant import AssistRequest, improve_brief
from realcenter_marketing.bootstrap.services import BusyError, CampaignService


def test_consultation_runs_only_creative_producer(settings, demo, tmp_path):
    demo.responses['BriefSuggestion'] = {'improved_request': 'Crie uma campanha de suco para o Feed, com foco no produto.', 'changes': ['Objetivo mais claro.'], 'questions': ['Qual é o período?']}
    request = AssistRequest(request='campanha suco', confirmed_facts=['Suco de laranja 2 L'])
    journal = RunJournal(tmp_path / 'assist')
    suggestion = asyncio.run(improve_brief(request, settings, journal, model=demo))
    assert suggestion.improved_request.startswith('Crie uma campanha')
    assert request.request == 'campanha suco'
    assert len(demo.calls) == 1
    name, instructions, data = demo.calls[0]
    assert name == 'BriefSuggestion'
    assert 'Você é Creative Producer' in instructions
    assert 'MODO ATUAL: assistência ao briefing' in instructions
    assert 'Suco de laranja 2 L' in json.dumps(data)
    usage = json.loads((journal.directory / 'usage.json').read_text())
    assert list(usage['text']['by_agent']) == ['Creative Producer']
    assert not (journal.directory / 'campaign.json').exists()


def test_consultation_failure_releases_lock_and_redacts(tmp_path, monkeypatch):
    monkeypatch.setattr('realcenter_marketing.bootstrap.settings.Settings.validate_live', lambda self: None)
    async def fail(*args, **kwargs):
        raise RuntimeError('private API response')
    monkeypatch.setattr('realcenter_marketing.bootstrap.services.improve_brief', fail)
    service = CampaignService(tmp_path)
    request = AssistRequest(request='Uma ideia')
    with pytest.raises(ValueError) as error:
        service.assist(request)
    assert 'private API response' not in str(error.value)
    assert service.lock.acquire(blocking=False)
    try:
        with pytest.raises(BusyError):
            service.assist(request)
    finally:
        service.lock.release()
    assert service.active_id is None
    assert not (tmp_path / 'campaigns/runs').exists()


def test_empty_consultation_is_rejected_before_api(tmp_path, monkeypatch):
    monkeypatch.setattr('realcenter_marketing.bootstrap.settings.Settings.validate_live', lambda self: None)
    with pytest.raises(ValueError, match='Escreva'):
        CampaignService(tmp_path).assist(AssistRequest(request='  '))
