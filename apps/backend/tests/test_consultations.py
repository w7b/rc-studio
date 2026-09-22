import asyncio
import json

import pytest
from agents import AgentOutputSchema, ModelBehaviorError

from realcenter_marketing.infrastructure.resources import load_manifest


@pytest.mark.parametrize('role', ['performance', 'marketing_analyst'])
def test_consultation_agents_are_active_without_tools(settings, demo, role):
    from realcenter_marketing.infrastructure.agents_sdk.team_factory import make_agent
    from realcenter_marketing.domain.consultations import OUTPUT_SCHEMAS
    assert load_manifest(settings.project_root, role).status == 'active'
    agent = make_agent(settings, role, OUTPUT_SCHEMAS[role], model=demo)
    assert agent.tools == []
    assert agent.handoffs == []
    AgentOutputSchema(agent.output_type)


def test_campaign_still_has_exactly_three_specialists_and_five_calls(settings, demo):
    from realcenter_marketing.application.orchestration import SPECIALIST_STEPS
    from realcenter_marketing.bootstrap.campaigns import create_campaign
    from realcenter_marketing.domain.campaigns import CampaignBrief
    assert [role for role, _ in SPECIALIST_STEPS] == ['social_media', 'copywriter', 'creative']
    asyncio.run(create_campaign(CampaignBrief(request='Campanha'), settings, model=demo))
    assert len(demo.calls) == 5


@pytest.mark.parametrize('role,schema', [('performance', 'PaidMediaPlan'), ('marketing_analyst', 'MarketingAnalysis')])
def test_invalid_output_is_repaired_once_and_never_saved(settings, demo, tmp_path, role, schema):
    from realcenter_marketing.domain.consultations import ConsultationRequest
    from realcenter_marketing.infrastructure.agents_sdk.consultations import execute_consultation
    from realcenter_marketing.infrastructure.observability.journal import RunJournal
    demo.responses[schema] = {'invented': 'invalid'}
    journal = RunJournal(tmp_path / 'consultation')
    with pytest.raises(ModelBehaviorError):
        asyncio.run(execute_consultation(ConsultationRequest(role=role, request='Ajude'), settings, journal, model=demo))
    assert len(demo.calls) == 2
    assert not (journal.directory / (role + '.json')).exists()
    assert not (journal.directory / 'result.json').exists()
    events = [json.loads(line)['event'] for line in (journal.directory / 'events.jsonl').read_text().splitlines()]
    assert 'validation_failed' in events
    assert 'repair_exhausted' in events


def analysis():
    return {'summary': 'Não recebi dados verificáveis.', 'findings': [], 'competitors': [],
            'seo_recommendations': [{'action': 'Verificar os títulos', 'rationale': 'Auditoria pendente',
                                     'priority': 'alta', 'verification': 'Revisão humana das páginas'}],
            'missing_data': ['Não recebi relatórios nem fontes verificáveis.']}


def media_plan():
    return {'objective': 'Planejar divulgação local',
            'audiences': [{'name': 'Público local', 'hypothesis': 'Interesse na loja',
                           'targeting': ['Região a confirmar'], 'exclusions': []}],
            'channels': ['Meta Ads, sujeito a confirmação'],
            'tests': [{'hypothesis': 'Mensagem objetiva atrai interesse',
                       'variants': ['Produto', 'Loja'], 'success_criterion': 'Comparar cliques medidos'}],
            'suggested_budget': {'amount_brl': None, 'period': 'A confirmar',
                                 'rationale': 'Falta limite de verba', 'approval_required': True},
            'measurement_plan': ['Definir conversão'], 'missing_data': ['Verba disponível']}


@pytest.mark.parametrize('role,schema,payload', [
    ('performance', 'PaidMediaPlan', media_plan()),
    ('marketing_analyst', 'MarketingAnalysis', analysis()),
])
def test_consultation_success_uses_one_call_and_separate_quota_and_journal(
        settings, demo, monkeypatch, role, schema, payload):
    from realcenter_marketing.bootstrap.services import CampaignService
    from realcenter_marketing.domain.consultations import ConsultationRequest
    from realcenter_marketing.infrastructure.agents_sdk.consultations import execute_consultation
    from realcenter_marketing.infrastructure.logs import usage_audit
    from test_quota import quota
    demo.responses[schema] = payload
    monkeypatch.setattr('realcenter_marketing.bootstrap.settings.Settings.validate_live', lambda self: None)

    async def execute(request, configured, journal, **kwargs):
        return await execute_consultation(request, settings, journal, model=demo)

    monkeypatch.setattr('realcenter_marketing.bootstrap.services.execute_consultation', execute)
    allowance = quota()
    service = CampaignService(settings.project_root, quota=allowance)
    try:
        response = service.consultations.run(ConsultationRequest(role=role, request='Ajude'))
        directory = settings.project_root / 'consultations' / response['id']
        assert json.loads((directory / 'result.json').read_text(encoding='utf-8')) == payload
        assert len(demo.calls) == 1
        assert response['usage']['text']['by_agent']
        assert usage_audit(settings.project_root)['records'][0]['kind'] == 'consultation'
        assert allowance.summary()['metrics']['assists']['used'] == 1
        assert allowance.summary()['metrics']['campaigns']['used'] == 0
        assert not (settings.project_root / 'campaigns/runs').exists()
        assert not service.busy
    finally:
        service.close()


@pytest.mark.parametrize('source_id,evidence', [('inventada', 'Cliques: 10'), ('relatorio', 'Cliques: 999')])
def test_analyst_rejects_unknown_sources_and_invented_evidence(source_id, evidence):
    from realcenter_marketing.domain.consultations import ConsultationRequest, validated_delivery
    request = ConsultationRequest(role='marketing_analyst', request='Analise', sources=[
        {'id': 'relatorio', 'title': 'Relatório local', 'content': 'Cliques: 10'}])
    output = analysis()
    output['findings'] = [{'source_id': source_id, 'evidence': evidence, 'analysis': 'Observação'}]
    with pytest.raises(ValueError, match='fonte ou trecho'):
        validated_delivery(request, output)


def test_analyst_accepts_supplied_evidence_and_requires_missing_data_without_sources():
    from realcenter_marketing.domain.consultations import ConsultationRequest, validated_delivery
    request = ConsultationRequest(role='marketing_analyst', request='Analise', sources=[
        {'id': 'relatorio', 'title': 'Relatório local', 'content': 'Cliques: 10'}])
    output = analysis()
    output['findings'] = [{'source_id': 'relatorio', 'evidence': 'Cliques: 10', 'analysis': 'Observação'}]
    assert validated_delivery(request, output).findings[0].source_id == 'relatorio'
    output = analysis()
    output['missing_data'] = []
    with pytest.raises(ValueError, match='dados verificáveis'):
        validated_delivery(ConsultationRequest(role='marketing_analyst', request='Analise'), output)


def test_semantic_failure_is_not_saved_and_releases_the_slot(settings, monkeypatch):
    from realcenter_marketing.bootstrap.services import CampaignService
    from realcenter_marketing.domain.consultations import ConsultationRequest
    monkeypatch.setattr('realcenter_marketing.bootstrap.settings.Settings.validate_live', lambda self: None)

    async def invalid(*args, **kwargs):
        output = analysis()
        output['competitors'] = [{'competitor': 'Inventado', 'source_id': 'fake',
                                  'evidence': 'Vendas: 999', 'analysis': 'Inventada'}]
        return output

    monkeypatch.setattr('realcenter_marketing.bootstrap.services.execute_consultation', invalid)
    service = CampaignService(settings.project_root)
    try:
        with pytest.raises(ValueError, match='Não foi possível'):
            service.consultations.run(ConsultationRequest(role='marketing_analyst', request='Analise'))
        assert not list((settings.project_root / 'consultations').glob('*/result.json'))
        assert not service.busy
        events = next((settings.project_root / 'consultations').glob('*/events.jsonl')).read_text(encoding='utf-8')
        assert 'consultation_failed' in events
    finally:
        service.close()


def test_consultation_quota_refusal_does_not_call_provider_or_create_journal(settings, monkeypatch):
    from realcenter_marketing.bootstrap.services import CampaignService
    from realcenter_marketing.domain.consultations import ConsultationRequest
    from realcenter_marketing.application.identity.quota import QuotaError
    from test_quota import quota
    monkeypatch.setattr('realcenter_marketing.bootstrap.settings.Settings.validate_live', lambda self: None)
    allowance = quota()
    allowance.reserve(assists=15)
    service = CampaignService(settings.project_root, quota=allowance)
    try:
        with pytest.raises(QuotaError):
            service.consultations.run(ConsultationRequest(role='performance', request='Planeje'))
        assert not (settings.project_root / 'consultations').exists()
        assert not service.busy
    finally:
        service.close()


def test_consultation_carries_model_tuning_and_scoped_brand(settings, demo):
    from types import SimpleNamespace
    from realcenter_marketing.infrastructure.agents_sdk.team_factory import make_agent
    from realcenter_marketing.domain.consultations import PaidMediaPlan
    option = SimpleNamespace(extra_body={'custom': 'value'}, max_output_tokens=2345)
    agent = make_agent(settings, 'performance', PaidMediaPlan, model=demo, option=option)
    assert agent.model_settings.extra_body == option.extra_body
    assert agent.model_settings.max_tokens == 2345
    instructions = agent.instructions(None, agent)
    assert 'visual-guidelines.md' not in instructions
    assert 'no_ad_spend' in instructions


def test_blank_extra_negative_and_duplicate_sources_are_rejected():
    from realcenter_marketing.domain.consultations import ConsultationRequest, PaidMediaPlan
    with pytest.raises(ValueError):
        ConsultationRequest(role='performance', request='  ')
    with pytest.raises(ValueError):
        PaidMediaPlan.model_validate({**media_plan(), 'extra': True})
    invalid = media_plan()
    invalid['suggested_budget']['amount_brl'] = -10
    with pytest.raises(ValueError):
        PaidMediaPlan.model_validate(invalid)
    with pytest.raises(ValueError):
        ConsultationRequest(role='marketing_analyst', request='Analise', sources=[
            {'id': '1', 'title': 'Fonte', 'content': 'Dado'}] * 2)


@pytest.mark.parametrize('role', ['performance', 'marketing_analyst'])
def test_factory_refuses_tools_even_for_consultations(settings, demo, monkeypatch, role):
    from realcenter_marketing.domain.consultations import OUTPUT_SCHEMAS
    from realcenter_marketing.infrastructure.agents_sdk.team_factory import make_agent
    manifest = load_manifest(settings.project_root, role).model_copy(update={'allowed_tools': ['forbidden']})
    monkeypatch.setattr('realcenter_marketing.infrastructure.agents_sdk.team_factory.load_manifest',
                        lambda *_: manifest)
    with pytest.raises(ValueError, match='tools'):
        make_agent(settings, role, OUTPUT_SCHEMAS[role], model=demo)


def test_failure_before_provider_returns_quota(settings, monkeypatch):
    from realcenter_marketing.bootstrap.services import CampaignService
    from realcenter_marketing.domain.consultations import ConsultationRequest
    from test_quota import quota
    monkeypatch.setattr('realcenter_marketing.bootstrap.settings.Settings.validate_live', lambda self: None)
    allowance = quota()
    service = CampaignService(settings.project_root, quota=allowance)

    def cannot_save():
        raise OSError('storage unavailable')

    monkeypatch.setattr(service.repository, 'create_consultation', cannot_save)
    try:
        with pytest.raises(OSError):
            service.consultations.run(ConsultationRequest(role='performance', request='Planeje'))
        assert allowance.summary()['metrics']['assists']['used'] == 0
        assert not service.busy
    finally:
        service.close()


def test_sdk_repair_can_recover_without_saving_unvalidated_artifacts(settings, demo, tmp_path, monkeypatch):
    from realcenter_marketing.domain.consultations import ConsultationRequest
    from realcenter_marketing.infrastructure.agents_sdk.consultations import execute_consultation
    from realcenter_marketing.infrastructure.observability.journal import RunJournal
    original = demo.get_response

    async def respond(*args, **kwargs):
        demo.responses['MarketingAnalysis'] = analysis() if demo.calls else {'invalid': True}
        return await original(*args, **kwargs)

    monkeypatch.setattr(demo, 'get_response', respond)
    journal = RunJournal(tmp_path / 'repair')
    result = asyncio.run(execute_consultation(
        ConsultationRequest(role='marketing_analyst', request='Analise'), settings, journal, model=demo))
    assert result.model_dump() == analysis()
    assert len(demo.calls) == 2
    assert not (journal.directory / 'marketing_analyst.json').exists()
    assert 'repair_completed' in (journal.directory / 'events.jsonl').read_text(encoding='utf-8')
