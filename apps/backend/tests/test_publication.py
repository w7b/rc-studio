import asyncio
import base64
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic import ValidationError

from realcenter_marketing.domain.publications import Publication, PRESETS
from realcenter_marketing.domain.campaigns import CampaignBrief
from realcenter_marketing.bootstrap.campaigns import create_campaign
from realcenter_marketing.infrastructure.image_generation import generate_feed
from realcenter_marketing.bootstrap.services import CampaignService, RunRequest
from realcenter_marketing.infrastructure.observability.journal import RunJournal
import time


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
    monkeypatch.setattr('realcenter_marketing.bootstrap.services.generate_feed', generate)
    with pytest.raises(RuntimeError): service._image(campaign,journal,None)
    assert calls == [1,2]
    fail[0]=False
    service._image(campaign,journal,None)
    assert calls == [1,2,2,3]
    assert len(json.loads((journal.directory/'carousel.json').read_text())['files']) == 3


def test_director_prefix_stable_and_specialists_keep_full_context(settings, demo):
    asyncio.run(create_campaign(CampaignBrief(request='Produto: teste',confirmed_facts=['Preço: R$ 3']),settings,model=demo))
    prompts=[c[1] for c in demo.calls if c[0]=='DirectorReview']
    assert len(prompts)==4 and len(set(prompts))==1
    copy=next(c[1] for c in demo.calls if c[0]=='CopyPack')
    assert demo.responses['SocialPlan']['strategy'] in copy
    assert 'Preço: R$ 3' in copy
