import base64
import io
import json
import threading
import time
from types import SimpleNamespace
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest
from PIL import Image

from realcenter_marketing.presentation.http.server import make_server
from realcenter_marketing.bootstrap.services import CampaignService, RunRequest, BusyError
from realcenter_marketing.infrastructure.persistence.filesystem import snapshot, run_directory
from realcenter_marketing.infrastructure.uploads import decode_upload
from realcenter_marketing.infrastructure.image_generation import generate_feed
from realcenter_marketing.domain.campaigns import CampaignBrief
from realcenter_marketing.bootstrap.campaigns import create_campaign
import asyncio


@pytest.fixture
def isolated_root(root, tmp_path):
    import shutil
    from realcenter_marketing.infrastructure.resources import resources_root, ROLE_FOLDERS
    resources = resources_root()
    for role in ('marketing_director', 'social_media', 'copywriter', 'creative', 'performance', 'marketing_analyst'):
        shutil.copytree(resources / 'agents' / ROLE_FOLDERS.get(role, role), tmp_path / 'agents' / role)
    for source, name in ((root / 'brand', 'brand'), (resources / 'policies', 'config'), (resources / 'demo', 'templates')):
        shutil.copytree(source, tmp_path / name)
    return tmp_path


@pytest.fixture
def png():
    out = io.BytesIO()
    Image.new('RGB', (1152, 1440), 'orange').save(out, format='PNG')
    return out.getvalue()


def wait_done(service):
    deadline = time.monotonic() + 10
    while service.active_id and time.monotonic() < deadline:
        time.sleep(.02)
    assert service.active_id is None


def test_demo_web_uploads_and_downloads(isolated_root, png):
    service = CampaignService(isolated_root)
    run_id = service.start(RunRequest(request='Campanha teste', mode='demo', upload=base64.b64encode(png).decode(), reference_upload=base64.b64encode(png).decode()))
    wait_done(service)
    directory = run_directory(isolated_root, run_id)
    assert (directory / 'product.png').read_bytes() == png
    assert (directory / 'reference.png').read_bytes() == png
    assert (directory / 'legenda-feed.txt').is_file()
    run = snapshot(isolated_root)[0]
    assert run['status'] == 'completed'
    assert run['outputs']['campaign']['delegation_log'] == ['social_media', 'copywriter', 'creative']
    assert run['usage']['text']['total_tokens'] == 0


def test_upload_rejects_disguised_or_broken_files():
    for payload in (b'<svg onload="evil()"/>', b'\x89PNG\r\n\x1a\nnot an image'):
        with pytest.raises(ValueError):
            decode_upload(base64.b64encode(payload).decode())


def test_retry_preserves_inputs_and_original(isolated_root, png, monkeypatch):
    service = CampaignService(isolated_root)
    import realcenter_marketing.bootstrap.services as module
    original = module.create_campaign
    async def fail(*args, **kwargs):
        raise RuntimeError('API unavailable')
    monkeypatch.setattr(module, 'create_campaign', fail)
    request = RunRequest(request='Minha campanha', confirmed_facts=['Preço R$ 14,98'], mode='demo',
                         upload=base64.b64encode(png).decode(), reference_upload=base64.b64encode(png).decode())
    old_id = service.start(request)
    wait_done(service)
    assert service.saved_request(old_id) == request
    monkeypatch.setattr(module, 'create_campaign', original)
    new_id = service.retry(old_id)
    wait_done(service)
    assert new_id != old_id
    assert service.saved_request(new_id) == request
    assert run_directory(isolated_root, old_id).is_dir()
    assert (run_directory(isolated_root, new_id) / 'campaign.json').is_file()
    with pytest.raises(ValueError, match='concluída'):
        service.retry(new_id)


def test_delete_is_scoped_and_blocks_active_work(isolated_root):
    service = CampaignService(isolated_root)
    run_id = service.start(RunRequest(request='Excluir este teste', mode='demo'))
    wait_done(service)
    service.lock.acquire()
    try:
        with pytest.raises(BusyError):
            service.delete(run_id)
    finally:
        service.lock.release()
    with pytest.raises(ValueError):
        service.delete('../brand')
    service.delete(run_id)
    assert not run_directory(isolated_root, run_id).exists()
    assert not snapshot(isolated_root)
    assert len(list((isolated_root / 'campaigns/runs/.trash').glob('run-*'))) == 1
    assert (isolated_root / 'brand').is_dir()


def test_retry_image_does_not_repeat_text_agents(isolated_root, settings, demo, monkeypatch):
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Campanha'), settings, model=demo))
    campaign.execution_mode = 'live'
    from realcenter_marketing.infrastructure.observability.journal import RunJournal
    directory = isolated_root / 'campaigns/runs' / ('run-' + 'a' * 32)
    journal = RunJournal(directory)
    journal.save('campaign', campaign)
    journal.emit('run_started', mode='live', image_requested=True)
    journal.emit('image_failed')
    calls = []
    monkeypatch.setattr('realcenter_marketing.bootstrap.settings.Settings.validate_live', lambda self: None)
    monkeypatch.setattr('realcenter_marketing.bootstrap.services.generate_feed', lambda *a, **kw: (calls.append('image') or directory / 'feed.png'))
    async def forbidden(*args, **kwargs):
        raise AssertionError('Text agents must not be rerun')
    monkeypatch.setattr('realcenter_marketing.bootstrap.services.create_campaign', forbidden)
    service = CampaignService(isolated_root)
    assert service.retry(directory.name) == directory.name
    wait_done(service)
    assert calls == ['image']
    assert snapshot(isolated_root)[0]['status'] == 'completed'


def test_only_one_job_and_lock_released(isolated_root, monkeypatch):
    service = CampaignService(isolated_root)
    gate = threading.Event()
    async def fail(*args, **kwargs):
        gate.wait(3)
        raise RuntimeError('secret provider payload')
    monkeypatch.setattr('realcenter_marketing.bootstrap.services.create_campaign', fail)
    service.start(RunRequest(request='Campanha', mode='demo'))
    with pytest.raises(BusyError):
        service.start(RunRequest(request='Segunda', mode='demo'))
    gate.set()
    wait_done(service)
    run = snapshot(isolated_root)[0]
    assert run['status'] == 'failed'
    assert 'secret provider payload' not in json.dumps(run)
    assert service.lock.acquire(blocking=False)
    service.lock.release()


def test_demo_cannot_spend_on_image(isolated_root):
    with pytest.raises(ValueError, match='Demonstração'):
        CampaignService(isolated_root).start(RunRequest(request='Teste', mode='demo', generate_image=True))


def test_image_failure_preserves_campaign(isolated_root, settings, demo, monkeypatch):
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Campanha'), settings, model=demo))
    campaign.execution_mode = 'live'
    service = CampaignService(isolated_root)
    async def prepared(*args, **kwargs):
        return campaign
    def fail(*args, **kwargs):
        raise RuntimeError('private image error')
    monkeypatch.setattr('realcenter_marketing.bootstrap.services.create_campaign', prepared)
    monkeypatch.setattr('realcenter_marketing.bootstrap.services.generate_feed', fail)
    monkeypatch.setattr('realcenter_marketing.bootstrap.settings.Settings.validate_live', lambda self: None)
    run_id = service.start(RunRequest(request='Campanha', generate_image=True))
    wait_done(service)
    directory = run_directory(isolated_root, run_id)
    assert (directory / 'campaign.json').is_file()
    run = snapshot(isolated_root)[0]
    assert run['status'] == 'failed'
    assert any(e['event'] == 'image_failed' for e in run['events'])
    assert 'private image error' not in json.dumps(run)


def test_image_adapter_uses_agent_deliveries_and_references(settings, demo, tmp_path, png):
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Campanha'), settings, model=demo))
    product = tmp_path / 'product.png'
    product.write_bytes(png)
    (tmp_path / 'reference.png').write_bytes(png)
    captured = {}
    def edit(**kwargs):
        captured.update(kwargs)
        captured['reference_names'] = [f.name for f in kwargs['image']]
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(png).decode())])
    path = generate_feed(campaign, settings, tmp_path, product, client=SimpleNamespace(images=SimpleNamespace(edit=edit)))
    assert Image.open(path).size == (1080, 1350)
    assert campaign.copywriting.headline in captured['prompt']
    assert campaign.creative.visual_direction in captured['prompt']
    assert captured['reference_names'][-1].endswith('reference.png')
    assert captured['n'] == 1
    assert not (tmp_path / 'brand-reference.png').exists()


def test_brand_reference_used_without_upload(settings, demo, tmp_path, png):
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Campanha'), settings, model=demo))
    captured = []
    def edit(**kwargs):
        captured.extend(f.name for f in kwargs['image'])
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(png).decode())])
    generate_feed(campaign, settings, tmp_path, client=SimpleNamespace(images=SimpleNamespace(edit=edit)))
    from realcenter_marketing.infrastructure.image_generation import brand_references
    expected = brand_references(settings.project_root)
    assert len(list(tmp_path.glob('brand-reference-*'))) == len(expected)
    assert all(path.read_bytes() in [copy.read_bytes() for copy in tmp_path.glob('brand-reference-*')] for path in expected)
    assert json.loads((tmp_path / 'reference-source.json').read_text())['source'] == 'brand'


def test_default_reference_missing_or_outside_folder_is_optional(tmp_path):
    from realcenter_marketing.infrastructure.image_generation import brand_reference
    assert brand_reference(tmp_path) is None
    directory = tmp_path / 'brand/references'
    directory.mkdir(parents=True)
    (tmp_path / 'outside.png').write_bytes(b'not used')
    (directory / 'default-visual.json').write_text(json.dumps({'file':'../../outside.png'}))
    assert brand_reference(tmp_path) is None


def test_http_guards_and_end_to_end(isolated_root):
    server = make_server(isolated_root, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    def get(path):
        return json.load(urlopen(base + path))
    try:
        config = get('/api/config')
        assert not config['configured']
        assert 'api_key' not in config
        data = json.dumps({'request': 'Teste pelo site', 'mode': 'demo'}).encode()
        for headers in ({'Content-Type': 'application/json'}, {'Content-Type': 'application/json', 'X-App-Token': config['token'], 'Origin': 'https://untrusted.example'}):
            with pytest.raises(HTTPError) as error:
                urlopen(Request(base + '/api/runs', data=data, headers=headers))
            assert error.value.code == 403
        request = Request(base + '/api/runs', data=data, headers={'Content-Type': 'application/json', 'X-App-Token': config['token']})
        run_id = json.load(urlopen(request))['id']
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            runs = get('/api/runs')
            if not runs['active_id']:
                break
            time.sleep(.03)
        assert runs['runs'][0]['status'] == 'completed'
        assert urlopen(base + f'/api/runs/{run_id}/files/legenda-feed.txt').status == 200
        for path in ('/.env', '/assets/../../.env', f'/api/runs/{run_id}/files/.env'):
            with pytest.raises(HTTPError) as error:
                urlopen(base + path)
            assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
