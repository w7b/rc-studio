"""Pipeline de campanha: planejamento, especialistas, revisão e prazos."""
import asyncio
import json
import pytest
from agents import AgentOutputSchema, ModelBehaviorError
from studio_ai.infrastructure.agents_sdk.team_factory import build_team, load_manifest
from studio_ai.domain.campaigns import Campaign, CampaignBrief, CopyPack, SocialPlan
from studio_ai.bootstrap.campaigns import create_campaign, save_campaign
from agents import ModelBehaviorError, Usage
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails
from studio_ai.infrastructure.observability.journal import RunJournal
from studio_ai.infrastructure.observability.costs import text_cost
from studio_ai.domain.campaigns import CampaignBrief
from studio_ai.bootstrap.campaigns import create_campaign
import base64
import io
from types import SimpleNamespace
from PIL import Image
from pydantic import ValidationError
from studio_ai.domain.publications import Publication, PRESETS
from studio_ai.infrastructure.image_generation import generate_feed
from studio_ai.bootstrap.services import CampaignService, RunRequest
import time
from studio_ai.bootstrap.settings import Settings
from studio_ai.infrastructure.agents_sdk.runtime import execute_campaign
from agents import ModelBehaviorError
from studio_ai.application.diagnostics import report


# ---- routing -----------------------------------------------------------------

def test_director_plans_then_specialists_run_then_director_reviews(settings, demo, tmp_path):
    result = asyncio.run(create_campaign(CampaignBrief(request="Crie uma campanha para o final de semana da Real Center."), settings, model=demo))
    # One plan, one call per specialist, one review. The Director no longer re-reads a
    # growing conversation between every delegation.
    assert [call[0] for call in demo.calls] == [
        "CampaignPlan", "SocialPlan", "CopyPack", "CreativeBrief", "DirectorReview",
    ]
    assert result.delegation_log == ["social_media", "copywriter", "creative"]
    assert result.social.model_dump() == demo.responses["SocialPlan"]
    assert result.copywriting.model_dump() == {**demo.responses["CopyPack"], 'carousel_cards': []}
    expected_creative = json.loads(json.dumps(demo.responses['CreativeBrief']))
    for asset in expected_creative['assets']:
        if asset['format'] == 'stories': asset['dimensions'] = '1080x1920 px (9:16)'
        if asset['format'] == 'feed': asset['dimensions'] = '1080x1350 px (4:5)'
    assert result.creative.model_dump() == expected_creative
    copy_context = next(c[1] for c in demo.calls if c[0] == "CopyPack")
    creative_context = next(c[1] for c in demo.calls if c[0] == "CreativeBrief")
    assert demo.responses["SocialPlan"]["strategy"] in copy_context
    assert demo.responses["CopyPack"]["headline"] in creative_context
    assert all("Brand Kit" in call[1] for call in demo.calls)
    path = save_campaign(result, tmp_path)
    assert Campaign.model_validate_json(path.read_text(encoding="utf-8")) == result
    assert save_campaign(result, tmp_path) != path


def test_no_agent_is_given_a_tool(settings, demo):
    """This is what lets a model outside OpenAI direct a campaign.

    Several providers disable tool calling as soon as the answer is constrained to a
    schema. The old Director needed both at once, which disqualified every model that
    made that trade. Nothing in the team holds a tool now, so the trade never comes up.
    """
    team = build_team(settings, model=demo)
    agents = {"planner": team.planner, "reviewer": team.reviewer, **team.specialists}
    for name, agent in agents.items():
        assert not agent.tools, f'{name} recebeu tools'
        assert not agent.handoffs, f'{name} recebeu handoffs'
        AgentOutputSchema(agent.output_type)
    # The manifest is the source of that claim, not just the construction above.
    assert not load_manifest(settings.project_root, "marketing_director").allowed_tools
    for role in ["performance", "marketing_analyst"]:
        assert load_manifest(settings.project_root, role).status == "active"
        assert role not in team.specialists


def test_specialists_run_in_order_and_a_failure_stops_the_pipeline(settings, demo):
    """Order used to be enforced by refusing out-of-turn tool calls. It is the loop now,
    and a specialist never starts before the previous delivery has validated."""
    demo.responses["CopyPack"]["stories"][0]["number"] = 99
    with pytest.raises(ValueError, match="corresponder"):
        asyncio.run(create_campaign(CampaignBrief(request="Campanha"), settings, model=demo))
    names = [call[0] for call in demo.calls]
    assert names.index("SocialPlan") < names.index("CopyPack") < names.index("CreativeBrief")


def test_an_incomplete_run_is_never_saved(settings, demo):
    """A runtime that returns fewer deliveries than the pipeline promises is refused."""
    from studio_ai.application.campaigns.create_campaign import create_campaign as compose
    from studio_ai.application.orchestration import AgentResult

    async def truncated(_brief):
        return AgentResult(demo.responses["DirectorReview"], {"social_media": object()}, ["social_media"])

    with pytest.raises(ValueError, match="sem concluir"):
        asyncio.run(compose(CampaignBrief(request="Campanha"), truncated, demo=True))


def test_invalid_specialist_output_fails(settings, demo):
    demo.responses["SocialPlan"]["stories"] = []
    with pytest.raises(ModelBehaviorError):
        asyncio.run(create_campaign(CampaignBrief(request="Campanha"), settings, model=demo))
    assert "CopyPack" not in [call[0] for call in demo.calls]


def test_outputs_forbid_extra_fields_and_blank_content(demo):
    data = dict(demo.responses["CopyPack"], price=10)
    with pytest.raises(ValueError):
        CopyPack.model_validate(data)
    with pytest.raises(ValueError):
        CampaignBrief(request="  ")
    data = json.loads(json.dumps(demo.responses["SocialPlan"]))
    data["stories"][1]["number"] = 1
    with pytest.raises(ValueError, match="consecutivos"):
        SocialPlan.model_validate(data)


def test_live_requires_configuration(settings):
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        asyncio.run(create_campaign(CampaignBrief(request="Campanha"), settings))


def test_brand_kit_is_scoped_to_what_each_role_acts_on(settings):
    """The kit is repeated in every agent's instructions, on every request it makes."""
    from studio_ai.infrastructure.resources import load_brand

    root = settings.project_root
    whole = json.loads(load_brand(root))
    creative = json.loads(load_brand(root, 'creative'))
    copywriter = json.loads(load_brand(root, 'copywriter'))

    def names(kit):
        # Keys are relative paths; chr(92) avoids an escape in this literal.
        return {key.split(chr(92))[-1].split('/')[-1] for key in kit}

    assert 'visual-guidelines.md' in names(creative), 'o Creative dirige a arte'
    assert 'visual-guidelines.md' not in names(copywriter), 'o Copywriter não desenha'
    assert {'brand.md', 'tone-of-voice.md'} <= names(copywriter)
    assert len(load_brand(root, 'copywriter')) < len(load_brand(root, 'creative'))
    # Folder documentation and the human review checklist never reach a prompt.
    assert not any(name.lower() in {'readme.md', 'quality-checklist.md'} for name in names(whole))
    # An unknown role keeps the whole kit rather than losing guidance silently.
    assert json.loads(load_brand(root, 'papel_inexistente')) == whole


# ---- progress ----------------------------------------------------------------

def test_each_agent_is_visible_and_caption_is_exported(settings, demo, tmp_path):
    events = []
    journal = RunJournal(tmp_path / "run", events.append)
    brief = CampaignBrief(request="Campanha", confirmed_facts=["Produto confirmado exclusivo"])
    campaign = asyncio.run(create_campaign(brief, settings, model=demo, journal=journal))
    # The Director appears twice: once planning, once reviewing.
    assert [e["agent"] for e in events if e["event"] == "started"] == [
        "Marketing Director", "Social Media Senior", "Copywriter Senior",
        "Creative Producer", "Marketing Director"]
    assert len([e for e in events if e["event"] == "completed"]) == 5
    assert (journal.directory / "legenda-feed.txt").read_text(encoding="utf-8").strip() == campaign.copywriting.feed_caption
    for role in ("social_media", "copywriter", "creative", "marketing_director",
                 "marketing_director_plan"):
        assert json.loads((journal.directory / f"{role}.json").read_text(encoding="utf-8"))
    assert all("Produto confirmado exclusivo" in call[1] for call in demo.calls)


def test_failure_preserves_prior_deliverables_and_safe_diagnostics(settings, demo, tmp_path):
    demo.responses["CreativeBrief"]["assets"] = []
    journal = RunJournal(tmp_path / "run")
    with pytest.raises(ModelBehaviorError):
        asyncio.run(create_campaign(CampaignBrief(request="Campanha"), settings, model=demo, journal=journal))
    assert (journal.directory / "copywriter.json").exists()
    assert (journal.directory / "legenda-feed.txt").exists()
    assert not (journal.directory / "campaign.json").exists()
    event = json.loads((journal.directory / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert event["agent"] == "Creative Producer"
    assert event["error_type"] == "ModelBehaviorError"
    # SDK redacts model validation payloads by default, including the cause.
    assert "input" not in event


def test_usage_and_astra_cost_are_recorded_per_agent(tmp_path):
    journal = RunJournal(tmp_path / "run")
    usage = Usage(requests=1, input_tokens=10_000, output_tokens=1_000, total_tokens=11_000,
                  input_tokens_details=InputTokensDetails(cached_tokens=2_000, cache_write_tokens=0),
                  output_tokens_details=OutputTokensDetails(reasoning_tokens=400))
    journal.record_usage("Copywriter Senior", "gpt-6-astra", usage)
    data = json.loads((journal.directory / "usage.json").read_text(encoding="utf-8"))
    assert data["text"]["input_tokens"] == 10_000
    assert data["text"]["cached_input_tokens"] == 2_000
    assert data["text"]["output_tokens"] == 1_000
    assert data["text"]["cost_usd"] == pytest.approx(.132)
    assert data["text"]["by_agent"]["Copywriter Senior"]["cost_usd"] == pytest.approx(.132)
    assert float(text_cost("gpt-6-astra", 10_000, 2_000, 0, 1_000)) == pytest.approx(.132)



def test_usage_survives_a_reader_holding_the_file(tmp_path, monkeypatch):
    """On Windows, replacing usage.json while GET /api/usage reads it raises
    PermissionError. That used to fail the whole campaign mid-run."""
    journal = RunJournal(tmp_path / "run")
    real_replace, refusals = type(tmp_path).replace, []

    def busy_then_free(self, target):
        if len(refusals) < 2:
            refusals.append(target)
            raise PermissionError(13, 'Acesso negado')
        return real_replace(self, target)

    monkeypatch.setattr(type(tmp_path), 'replace', busy_then_free)
    journal.record_usage("Agent", "custom-model", Usage(requests=1, input_tokens=5,
                         output_tokens=2, total_tokens=7))
    assert len(refusals) == 2
    data = json.loads((journal.directory / "usage.json").read_text(encoding="utf-8"))
    assert data["text"]["total_tokens"] == 7

    # A file that stays locked is a real fault: it surfaces instead of looping forever.
    monkeypatch.setattr(type(tmp_path), 'replace',
                        lambda self, target: (_ for _ in ()).throw(PermissionError(13, 'x')))
    with pytest.raises(PermissionError):
        journal.record_usage("Agent", "custom-model", Usage(requests=1, input_tokens=1,
                             output_tokens=1, total_tokens=2))

def test_unknown_model_keeps_tokens_without_inventing_price(tmp_path):
    journal = RunJournal(tmp_path / "run")
    journal.record_usage("Agent", "custom-model", Usage(requests=1, input_tokens=5,
                         output_tokens=2, total_tokens=7))
    data = json.loads((journal.directory / "usage.json").read_text(encoding="utf-8"))
    assert data["text"]["total_tokens"] == 7
    assert data["text"]["cost_usd"] is None


# ---- publication -------------------------------------------------------------

@pytest.mark.parametrize('preset', list(PRESETS))
def test_final_dimensions_and_prompt_use_publication(preset, settings, demo, tmp_path):
    publication = Publication(preset=preset, kind=PRESETS[preset]['types'][0])
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Oferta', publication=publication), settings, model=demo))
    captured = {}
    def respond(**kwargs):
        captured.update(kwargs)
        data = io.BytesIO()
        Image.new('RGB', tuple(map(int, kwargs['size'].split('x'))), 'red').save(data, 'PNG')
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(data.getvalue()).decode())])
    client = SimpleNamespace(images=SimpleNamespace(edit=respond, generate=respond))
    path = generate_feed(campaign, settings, tmp_path, client=client)
    assert Image.open(path).size == publication.dimensions
    assert publication.kind in captured['prompt']
    assert json.loads(path.with_suffix('.json').read_text())['publication'] == publication.model_dump()


def test_invalid_pairs_and_slide_counts_rejected():
    for payload in ({'kind':'story'}, {'kind':'carousel','slides':1}, {'slides':3}, {'kind':'carousel','slides':11}):
        with pytest.raises(ValidationError): Publication(**payload)


def test_demo_carousel_request_roundtrip(settings, tmp_path):
    import shutil
    for name in ('agents', 'brand', 'config', 'templates'):
        shutil.copytree(settings.project_root/name, tmp_path/name)
    service = CampaignService(tmp_path)
    request = RunRequest(request='Carrossel teste', mode='demo', publication=Publication(kind='carousel',preset='feed_square',slides=4))
    run_id = service.start(request)
    deadline = time.monotonic()+10
    while service.active_id and time.monotonic() < deadline: time.sleep(.01)
    assert service.active_id is None
    assert service.saved_request(run_id) == request
    campaign = json.loads((tmp_path/'campaigns/runs'/run_id/'campaign.json').read_text(encoding='utf-8'))
    assert len(campaign['copywriting']['carousel_cards']) == 4


def test_low_resolution_rejected_but_usage_observed(settings, demo, tmp_path):
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Oferta'), settings, model=demo))
    data = io.BytesIO(); Image.new('RGB',(2,2)).save(data,'PNG')
    response = SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(data.getvalue()).decode())])
    client = SimpleNamespace(images=SimpleNamespace(edit=lambda **kw: response, generate=lambda **kw: response))
    calls = []
    with pytest.raises(ValueError, match='resolução inferior'):
        generate_feed(campaign, settings, tmp_path, client=client, on_response=lambda *args: calls.append(args))
    assert len(calls) == 1
    assert not list(tmp_path.glob('feed-*.png'))


def test_carousel_resume_preserves_finished_cards(settings, demo, tmp_path, monkeypatch):
    publication = Publication(kind='carousel', slides=3)
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Oferta',publication=publication), settings, model=demo))
    journal = RunJournal(tmp_path/'run')
    service = CampaignService(tmp_path)
    calls=[]
    fail = [True]
    def generate(*args, card=None, style_image=None, **kwargs):
        calls.append(card.number)
        if card.number == 2 and fail[0]: raise RuntimeError('stop')
        if card.number > 1: assert style_image and style_image.is_file()
        path=journal.directory/f'carousel-{card.number:02d}-test.png'; path.write_bytes(b'image')
        return path
    monkeypatch.setattr('studio_ai.bootstrap.services.generate_feed', generate)
    with pytest.raises(RuntimeError): service._image(campaign,journal,None)
    assert calls == [1,2]
    fail[0]=False
    service._image(campaign,journal,None)
    assert calls == [1,2,2,3]
    assert len(json.loads((journal.directory/'carousel.json').read_text())['files']) == 3


def test_director_prefix_stable_and_specialists_keep_full_context(settings, demo):
    asyncio.run(create_campaign(CampaignBrief(request='Produto: teste',confirmed_facts=['Preço: R$ 3']),settings,model=demo))
    # Planning and reviewing share one manifest and one set of instructions, so the
    # Director's prefix is byte-identical across both of its calls and stays cacheable.
    prompts=[c[1] for c in demo.calls if c[0] in ('CampaignPlan','DirectorReview')]
    assert len(prompts)==2 and len(set(prompts))==1
    copy=next(c[1] for c in demo.calls if c[0]=='CopyPack')
    assert demo.responses['SocialPlan']['strategy'] in copy
    assert 'Preço: R$ 3' in copy


# ---- agent_timeout -----------------------------------------------------------

def test_agent_timeout_default(settings):
    assert settings.agent_timeout_seconds == 600


def test_agent_timeout_can_be_configured(root, monkeypatch):
    monkeypatch.setenv('AGENT_TIMEOUT_SECONDS', '45')
    assert Settings.load(root).agent_timeout_seconds == 45


def test_slow_copywriter_is_cancelled_and_named_without_running_next_agent(settings, demo, tmp_path, monkeypatch):
    # A shorter test clock; production settings still enforce their minimum of 30s.
    settings = settings.model_copy(update={'agent_timeout_seconds': .5})
    original = demo.get_response
    cancelled = []

    async def slow(*args, **kwargs):
        if len(demo.calls) == 2:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.append(True)
                raise
        return await original(*args, **kwargs)

    monkeypatch.setattr(demo, 'get_response', slow)
    journal = RunJournal(tmp_path / 'timeout')
    started = time.monotonic()
    with pytest.raises(TimeoutError, match=r'Copywriter.*0.5s'):
        asyncio.run(execute_campaign(CampaignBrief(request='Teste'), settings, model=demo, journal=journal))
    assert time.monotonic() - started < 4
    assert cancelled == [True]
    assert len(demo.calls) == 2
    events = [json.loads(line) for line in (journal.directory / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
    assert events[-1]['event'] == 'failed'
    assert 'Copywriter' in json.dumps(events[-1])
    assert not any(event['event'] == 'repair_started' for event in events)


# ---- diagnostics -------------------------------------------------------------

def test_failed_specialist_repairs_once_without_repeating_previous_agents(settings, demo, tmp_path):
    original = demo.get_response
    attempts = []
    async def respond(*args, **kwargs):
        schema = kwargs['output_schema'].output_type.__name__
        attempts.append(schema)
        response = await original(*args, **kwargs)
        if schema == 'CopyPack' and attempts.count('CopyPack') == 1:
            value = json.loads(response.output[0].content[0].text)
            value['stories'] = []
            response.output[0].content[0].text = json.dumps(value)
        return response
    demo.get_response = respond
    journal = RunJournal(tmp_path / 'run')
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Teste'), settings, model=demo, journal=journal))
    assert campaign.copywriting.feed_caption
    assert attempts.count('CopyPack') == 2
    assert attempts.count('SocialPlan') == 1
    assert attempts.count('CreativeBrief') == 1
    events = [json.loads(line) for line in (journal.directory / 'events.jsonl').read_text().splitlines()]
    failure = next(e for e in events if e['event'] == 'validation_failed')
    assert failure['schema'] == 'CopyPack'
    assert failure['validation_errors'][0]['location'] == ['stories']
    assert failure['validation_errors'][0]['type'] == 'too_short'
    assert sum(e['event'] == 'repair_started' for e in events) == 1
    assert any(e['event'] == 'repair_completed' for e in events)
    copy_calls = [call for call in demo.calls if call[0] == 'CopyPack']
    assert 'CORREÇÃO DE FORMATO' in json.dumps(copy_calls[1][2], ensure_ascii=False)
    assert report('run', events, None, {})['recovered']


def test_repair_stops_after_one_extra_call_and_does_not_log_content(settings, demo, tmp_path):
    demo.responses['CopyPack']['stories'] = []
    demo.responses['CopyPack']['headline'] = 'PRIVATE-OUTPUT-MARKER'
    journal = RunJournal(tmp_path / 'run')
    with pytest.raises(ModelBehaviorError):
        asyncio.run(create_campaign(CampaignBrief(request='Teste'), settings, model=demo, journal=journal))
    assert len([call for call in demo.calls if call[0] == 'CopyPack']) == 2
    logs = (journal.directory / 'events.jsonl').read_text()
    assert 'repair_exhausted' in logs
    assert 'PRIVATE-OUTPUT-MARKER' not in logs
    assert (journal.directory / 'social_media.json').is_file()
    assert not (journal.directory / 'copywriter.json').exists()


def test_historical_diagnostics_are_explicit_about_missing_data():
    data = report('run-old', [{'event':'run_failed','error_type':'ModelBehaviorError','agent':'Copywriter','time':'2026-09-09'}], None, {'social_media': {}})
    assert data['historical_note']
    assert not data['details_available']
    assert data['validation_errors'] == []
    assert data['saved_outputs'] == ['social_media']
    assert data['retry_scope'] == 'full_campaign'
