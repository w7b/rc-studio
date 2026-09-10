import asyncio
import base64
import io
from types import SimpleNamespace

import pytest
from PIL import Image

from realcenter_marketing.infrastructure.image_generation import generate_feed
from realcenter_marketing.bootstrap.services import CampaignService, ImageRequest
from realcenter_marketing.bootstrap.campaigns import create_campaign
from realcenter_marketing.domain.campaigns import CampaignBrief


def test_revision_passes_base_and_changes_and_preserves_original(settings, demo, tmp_path):
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Campanha'), settings, model=demo))
    data=io.BytesIO()
    Image.new('RGB',(1152,1440),'red').save(data,'PNG')
    original=tmp_path/'feed-original.png'
    original.write_bytes(data.getvalue())
    reference=tmp_path/'demonstracao.png'
    reference.write_bytes(data.getvalue())
    captured={}
    def edit(**kwargs):
        captured.update(kwargs)
        captured['names']=[image.name for image in kwargs['image']]
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(data.getvalue()).decode())])
    result=generate_feed(campaign,settings,tmp_path,client=SimpleNamespace(images=SimpleNamespace(edit=edit)),changes='Troque o fundo para azul',base_image=original,revision_reference=reference)
    assert captured['names'][0]==str(original)
    assert 'Troque o fundo para azul' in captured['prompt']
    assert original.read_bytes()==data.getvalue()
    assert result != original
    assert result.with_suffix('.json').is_file()
    assert str(reference) in captured['names']
    assert 'Demonstração enviada para ESTA revisão' in captured['prompt']
    import json
    assert {'source':'revision_upload','file':'demonstracao.png'} in json.loads(result.with_suffix('.json').read_text(encoding='utf-8'))['references']


def test_revision_requires_image_from_same_run(tmp_path):
    service=CampaignService(tmp_path)
    with pytest.raises(ValueError,match='Selecione uma arte'):
        service.image('run-'+'a'*32,ImageRequest(base_image_id='unknown',changes='Mude a cor'))
    with pytest.raises(ValueError,match='imagem base'):
        service.image('run-'+'a'*32,ImageRequest(changes='Mude a cor'))


def test_revision_upload_is_scoped_to_one_request_and_keeps_original(settings, demo, tmp_path, monkeypatch):
    import time
    from realcenter_marketing.infrastructure.observability.journal import RunJournal
    from realcenter_marketing.infrastructure.persistence.filesystem import media_catalog
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Campanha'), settings, model=demo))
    campaign.execution_mode = 'live'
    run_id = 'run-'+'b'*32
    directory = tmp_path/'campaigns/runs'/run_id
    journal=RunJournal(directory); journal.save('campaign', campaign)
    data=io.BytesIO(); Image.new('RGB',(8,8),'blue').save(data,'PNG')
    (directory/'feed-original.png').write_bytes(data.getvalue())
    (directory/'reference.png').write_bytes(data.getvalue())
    base=next(m['id'] for m in media_catalog(tmp_path).values() if m['name']=='feed-original.png')
    service=CampaignService(tmp_path)
    calls=[]
    def fake(*args):
        calls.append(args[-1])
        if args[-1]: assert args[-1].read_bytes()==data.getvalue()
    monkeypatch.setattr(service,'_image',fake)
    monkeypatch.setattr('realcenter_marketing.bootstrap.settings.Settings.validate_live',lambda self: None)
    for upload in (base64.b64encode(data.getvalue()).decode(), None):
        service.image(run_id,ImageRequest(base_image_id=base,changes='Mude o fundo',reference_upload=upload))
        deadline=time.monotonic()+5
        while service.active_id and time.monotonic()<deadline: time.sleep(.01)
        assert service.active_id is None
    assert calls[0].parent==directory/'revision-inputs'
    assert calls[1] is None
    assert (directory/'reference.png').read_bytes()==data.getvalue()
    assert (directory/'feed-original.png').read_bytes()==data.getvalue()


def test_revision_rejects_invalid_demo_upload_before_running(tmp_path):
    service=CampaignService(tmp_path)
    with pytest.raises(ValueError):
        service.image('run-'+'a'*32,ImageRequest(reference_upload=base64.b64encode(b'not an image').decode()))
    assert service.active_id is None
