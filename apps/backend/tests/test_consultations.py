"""Consultoria de marketing sob demanda."""
import asyncio
import json
import pytest
from agents import AgentOutputSchema, ModelBehaviorError
from studio_ai.infrastructure.resources import load_manifest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from test_identity import shared, sign_in
from concurrent.futures import ThreadPoolExecutor
import threading
from studio_ai.application.consultations import ConsultationService
from studio_ai.domain.consultations import ConsultationRequest
from studio_ai.infrastructure.execution import ExecutionPool
from studio_ai.infrastructure.persistence.campaign_repository import FileCampaignRepository
from test_identity import quota


# ---- consultations -----------------------------------------------------------

@pytest.mark.parametrize('role', ['performance', 'marketing_analyst'])
def test_consultation_agents_are_active_without_tools(settings, demo, role):
    from studio_ai.infrastructure.agents_sdk.team_factory import make_agent
    from studio_ai.domain.consultations import OUTPUT_SCHEMAS
    assert load_manifest(settings.project_root, role).status == 'active'
    agent = make_agent(settings, role, OUTPUT_SCHEMAS[role], model=demo)
    assert agent.tools == []
    assert agent.handoffs == []
    AgentOutputSchema(agent.output_type)


def test_campaign_still_has_exactly_three_specialists_and_five_calls(settings, demo):
    from studio_ai.application.orchestration import SPECIALIST_STEPS
    from studio_ai.bootstrap.campaigns import create_campaign
    from studio_ai.domain.campaigns import CampaignBrief
    assert [role for role, _ in SPECIALIST_STEPS] == ['social_media', 'copywriter', 'creative']
    asyncio.run(create_campaign(CampaignBrief(request='Campanha'), settings, model=demo))
    assert len(demo.calls) == 5


@pytest.mark.parametrize('role,schema', [('performance', 'PaidMediaPlan'), ('marketing_analyst', 'MarketingAnalysis')])
def test_invalid_output_is_repaired_once_and_never_saved(settings, demo, tmp_path, role, schema):
    from studio_ai.domain.consultations import ConsultationRequest
    from studio_ai.infrastructure.agents_sdk.consultations import execute_consultation
    from studio_ai.infrastructure.observability.journal import RunJournal
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
    from studio_ai.bootstrap.services import CampaignService
    from studio_ai.domain.consultations import ConsultationRequest
    from studio_ai.infrastructure.agents_sdk.consultations import execute_consultation
    from studio_ai.infrastructure.logs import usage_audit
    from test_identity import quota
    demo.responses[schema] = payload
    monkeypatch.setattr('studio_ai.bootstrap.settings.Settings.validate_live', lambda self: None)

    async def execute(request, configured, journal, **kwargs):
        return await execute_consultation(request, settings, journal, model=demo)

    monkeypatch.setattr('studio_ai.bootstrap.services.execute_consultation', execute)
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
    from studio_ai.domain.consultations import ConsultationRequest, validated_delivery
    request = ConsultationRequest(role='marketing_analyst', request='Analise', sources=[
        {'id': 'relatorio', 'title': 'Relatório local', 'content': 'Cliques: 10'}])
    output = analysis()
    output['findings'] = [{'source_id': source_id, 'evidence': evidence, 'analysis': 'Observação'}]
    with pytest.raises(ValueError, match='fonte ou trecho'):
        validated_delivery(request, output)


def test_analyst_accepts_supplied_evidence_and_requires_missing_data_without_sources():
    from studio_ai.domain.consultations import ConsultationRequest, validated_delivery
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
    from studio_ai.bootstrap.services import CampaignService
    from studio_ai.domain.consultations import ConsultationRequest
    monkeypatch.setattr('studio_ai.bootstrap.settings.Settings.validate_live', lambda self: None)

    async def invalid(*args, **kwargs):
        output = analysis()
        output['competitors'] = [{'competitor': 'Inventado', 'source_id': 'fake',
                                  'evidence': 'Vendas: 999', 'analysis': 'Inventada'}]
        return output

    monkeypatch.setattr('studio_ai.bootstrap.services.execute_consultation', invalid)
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
    from studio_ai.bootstrap.services import CampaignService
    from studio_ai.domain.consultations import ConsultationRequest
    from studio_ai.application.identity.quota import QuotaError
    from test_identity import quota
    monkeypatch.setattr('studio_ai.bootstrap.settings.Settings.validate_live', lambda self: None)
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
    from studio_ai.infrastructure.agents_sdk.team_factory import make_agent
    from studio_ai.domain.consultations import PaidMediaPlan
    option = SimpleNamespace(extra_body={'custom': 'value'}, max_output_tokens=2345)
    agent = make_agent(settings, 'performance', PaidMediaPlan, model=demo, option=option)
    assert agent.model_settings.extra_body == option.extra_body
    assert agent.model_settings.max_tokens == 2345
    instructions = agent.instructions(None, agent)
    assert 'visual-guidelines.md' not in instructions
    assert 'no_ad_spend' in instructions


def test_blank_extra_negative_and_duplicate_sources_are_rejected():
    from studio_ai.domain.consultations import ConsultationRequest, PaidMediaPlan
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
    from studio_ai.domain.consultations import OUTPUT_SCHEMAS
    from studio_ai.infrastructure.agents_sdk.team_factory import make_agent
    manifest = load_manifest(settings.project_root, role).model_copy(update={'allowed_tools': ['forbidden']})
    monkeypatch.setattr('studio_ai.infrastructure.agents_sdk.team_factory.load_manifest',
                        lambda *_: manifest)
    with pytest.raises(ValueError, match='tools'):
        make_agent(settings, role, OUTPUT_SCHEMAS[role], model=demo)


def test_failure_before_provider_returns_quota(settings, monkeypatch):
    from studio_ai.bootstrap.services import CampaignService
    from studio_ai.domain.consultations import ConsultationRequest
    from test_identity import quota
    monkeypatch.setattr('studio_ai.bootstrap.settings.Settings.validate_live', lambda self: None)
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
    from studio_ai.domain.consultations import ConsultationRequest
    from studio_ai.infrastructure.agents_sdk.consultations import execute_consultation
    from studio_ai.infrastructure.observability.journal import RunJournal
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


# ---- consultations_http ------------------------------------------------------

def post(base, cookie, csrf, payload):
    return urlopen(Request(base + '/api/consultations', data=json.dumps(payload).encode(), headers={
        'Content-Type': 'application/json', 'Origin': base,
        'Cookie': cookie, 'X-App-Token': csrf}))


@pytest.mark.parametrize('role', ['OWNER', 'PAID', 'DEFAULT'])
def test_consultation_uses_session_role_and_tenant_module(shared, monkeypatch, role):
    server, base, store = shared
    tenant = store.tenant_by_slug('mercado-central')
    user = store.user_by_email('dono@loja.com.br')
    store.grant(user.id, tenant.id, role)
    cookie, csrf, _ = sign_in(base)
    seen = []

    def consult(context, request):
        seen.append((context.slug, context.binding, request.role, request.model_id))
        return {'result': 'validated'}

    monkeypatch.setattr('studio_ai.bootstrap.registry.TenantContext.consult', consult)
    payload = {'role': 'performance', 'request': 'Planeje', 'model_id': 'opaque:model'}
    store.set_module(tenant.id, 'marketing', False)
    with pytest.raises(HTTPError) as refused:
        post(base, cookie, csrf, payload)
    assert refused.value.code == 403
    assert seen == []
    store.set_module(tenant.id, 'marketing', True)
    # Campaign entitlement does not control this independent module.
    store.set_module(tenant.id, 'campaigns', False)
    assert json.load(post(base, cookie, csrf, payload)) == {'result': 'validated'}
    assert seen[0][0] == tenant.slug
    assert seen[0][1][1:] == (tenant.id, role)
    assert seen[0][2:] == ('performance', 'opaque:model')


def test_consultation_requires_session_csrf_and_valid_request(shared, monkeypatch):
    _, base, _ = shared
    payload = {'role': 'marketing_analyst', 'request': 'Analise'}
    with pytest.raises(HTTPError) as anonymous:
        post(base, '', '', payload)
    assert anonymous.value.code == 401
    cookie, csrf, _ = sign_in(base)
    with pytest.raises(HTTPError) as no_csrf:
        post(base, cookie, '', payload)
    assert no_csrf.value.code == 403
    for invalid in ({'role': 'marketing_director', 'request': 'Analise'},
                    {**payload, 'request': '  '}, {**payload, 'tenant_id': 999}):
        with pytest.raises(HTTPError) as bad:
            post(base, cookie, csrf, invalid)
        assert bad.value.code == 400


# ---- consultation_concurrency ------------------------------------------------

@pytest.mark.parametrize('shutdown', [False, True])
def test_consultations_share_global_capacity_and_refund_discarded_work(tmp_path, shutdown):
    pool = ExecutionPool(capacity=1)
    hold, first_started, second_started, submitted = (threading.Event() for _ in range(4))
    allowance = quota()

    def service(key, entered, quota=None):
        async def execute(*args):
            entered.set()
            assert hold.wait(5)
            return media_plan()
        scheduler = pool.scheduler(key)
        if key == 'second':
            original = scheduler.acquire
            def acquire():
                result = original()
                submitted.set()
                return result
            scheduler.acquire = acquire
        return ConsultationService(FileCampaignRepository(tmp_path / key), scheduler, execute,
                                   lambda request: None, quota)

    first, second = service('first', first_started), service('second', second_started, allowance)
    request = ConsultationRequest(role='performance', request='Planeje')
    with ThreadPoolExecutor(max_workers=2) as callers:
        a = callers.submit(first.run, request)
        b = None
        try:
            assert first_started.wait(3)
            b = callers.submit(second.run, request)
            assert submitted.wait(3)
            assert not second_started.wait(.15), 'second provider bypassed the global capacity'
            if shutdown:
                pool.close(timeout=.01)
            hold.set()
            assert a.result(3)['role'] == 'performance'
            if shutdown:
                with pytest.raises(ValueError, match='Não foi possível'):
                    b.result(3)
                assert not second_started.is_set()
                assert allowance.summary()['metrics']['assists']['used'] == 0
            else:
                assert b.result(3)['role'] == 'performance'
                assert second_started.is_set()
                assert allowance.summary()['metrics']['assists']['used'] == 1
            assert not first.scheduler.lock.locked()
            assert not second.scheduler.lock.locked()
        finally:
            hold.set()
            pool.close(timeout=3)


def test_shutdown_between_acquire_and_enqueue_returns_instead_of_hanging(tmp_path):
    pool = ExecutionPool(capacity=1)
    warm = pool.scheduler('warm')
    finished = threading.Event()
    assert warm.acquire()
    warm.submit(lambda: (warm.release(), finished.set()))
    assert finished.wait(3)
    scheduler = pool.scheduler('late')
    allowance = quota()
    repository = FileCampaignRepository(tmp_path)
    create = repository.create_consultation

    def close_during_setup():
        pool.close(timeout=.05)
        return create()

    repository.create_consultation = close_during_setup
    async def forbidden(*args):
        pytest.fail('provider must not start after shutdown')
    service = ConsultationService(repository, scheduler, forbidden, lambda _: None, allowance)
    done, errors = threading.Event(), []

    def caller():
        try:
            service.run(ConsultationRequest(role='performance', request='Planeje'))
        except Exception as exc:
            errors.append(exc)
        finally:
            done.set()

    thread = threading.Thread(target=caller, daemon=True)
    thread.start()
    assert done.wait(3), 'synchronous caller stranded behind shutdown sentinels'
    thread.join(1)
    assert len(errors) == 1 and isinstance(errors[0], ValueError)
    assert allowance.summary()['metrics']['assists']['used'] == 0
    assert not scheduler.lock.locked()
