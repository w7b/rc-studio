"""Contratos HTTP, proxy, contrato com o frontend e assistente de briefing."""
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
from studio_ai.presentation.http.server import make_server
from studio_ai.bootstrap.services import CampaignService, RunRequest, BusyError
from studio_ai.infrastructure.persistence.filesystem import snapshot, run_directory
from studio_ai.infrastructure.uploads import decode_upload
from studio_ai.infrastructure.image_generation import generate_feed
from studio_ai.domain.campaigns import CampaignBrief
from studio_ai.bootstrap.campaigns import create_campaign
import asyncio
import socket
from studio_ai.presentation.http.proxy import client_address
from pathlib import Path
import re
import subprocess
from studio_ai.application.commands import RunRequest
import hashlib
from urllib.request import urlopen
from studio_ai.bootstrap.paths import AppPaths
from studio_ai.infrastructure.persistence.filesystem import media_catalog, snapshot
from studio_ai.infrastructure.resources import agent_directory, load_manifest, prompt_version
from studio_ai.infrastructure.observability.journal import RunJournal
from studio_ai.infrastructure.agents_sdk.brief_assistant import AssistRequest, improve_brief
from studio_ai.bootstrap.services import BusyError, CampaignService


# ---- web ---------------------------------------------------------------------

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
    import studio_ai.bootstrap.services as module
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
    from studio_ai.infrastructure.observability.journal import RunJournal
    directory = isolated_root / 'campaigns/runs' / ('run-' + 'a' * 32)
    journal = RunJournal(directory)
    journal.save('campaign', campaign)
    journal.emit('run_started', mode='live', image_requested=True)
    journal.emit('image_failed')
    calls = []
    monkeypatch.setattr('studio_ai.bootstrap.settings.Settings.validate_live', lambda self: None)
    monkeypatch.setattr('studio_ai.bootstrap.services.generate_feed', lambda *a, **kw: (calls.append('image') or directory / 'feed.png'))
    async def forbidden(*args, **kwargs):
        raise AssertionError('Text agents must not be rerun')
    monkeypatch.setattr('studio_ai.bootstrap.services.create_campaign', forbidden)
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
    monkeypatch.setattr('studio_ai.bootstrap.services.create_campaign', fail)
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
    monkeypatch.setattr('studio_ai.bootstrap.services.create_campaign', prepared)
    monkeypatch.setattr('studio_ai.bootstrap.services.generate_feed', fail)
    monkeypatch.setattr('studio_ai.bootstrap.settings.Settings.validate_live', lambda self: None)
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
    from studio_ai.infrastructure.image_generation import brand_references
    expected = brand_references(settings.project_root)
    assert len(list(tmp_path.glob('brand-reference-*'))) == len(expected)
    assert all(path.read_bytes() in [copy.read_bytes() for copy in tmp_path.glob('brand-reference-*')] for path in expected)
    assert json.loads((tmp_path / 'reference-source.json').read_text())['source'] == 'brand'


def test_default_reference_missing_or_outside_folder_is_optional(tmp_path):
    from studio_ai.infrastructure.image_generation import brand_reference
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


# ---- proxy -------------------------------------------------------------------

@pytest.mark.parametrize('forwarded', [None, '', 'not-an-ip', '203.0.113.1, 203.0.113.2', '203.0.113.1:80'])
def test_proxy_rejects_missing_malformed_and_chained_addresses(forwarded):
    assert client_address('192.0.2.1', forwarded, ('192.0.2.1',)) == '192.0.2.1'


def test_untrusted_peer_cannot_choose_its_rate_limit_identity():
    assert client_address('192.0.2.99', '203.0.113.1', ('192.0.2.1',)) == '192.0.2.99'
    assert client_address('127.0.0.1', '203.0.113.1', ()) == '127.0.0.1'


def test_proxy_follows_dns_replacement_without_trusting_the_old_address(monkeypatch):
    address = '192.0.2.1'
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs:
                        [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (address, 0))])
    assert client_address('192.0.2.1', '203.0.113.1', ('nginx',)) == '203.0.113.1'
    address = '192.0.2.2'
    assert client_address('192.0.2.1', '203.0.113.1', ('nginx',)) == '192.0.2.1'
    assert client_address('192.0.2.2', '203.0.113.1', ('nginx',)) == '203.0.113.1'


def test_dns_failure_falls_back_to_socket_address(monkeypatch):
    def unavailable(*args, **kwargs):
        raise socket.gaierror('unavailable')
    monkeypatch.setattr(socket, 'getaddrinfo', unavailable)
    assert client_address('192.0.2.1', '203.0.113.1', ('nginx',)) == '192.0.2.1'


def test_ipv6_is_canonical_for_a_trusted_peer():
    assert client_address('::1', '2001:0db8:0:0:0:0:0:1', ('::1',)) == '2001:db8::1'


# ---- frontend_contract -------------------------------------------------------

REPO = Path(__file__).resolve().parents[3]


def test_campaign_form_payloads_match_run_request():
    form = (REPO / 'apps/frontend/src/features/campaigns/CampaignForm.jsx').read_text(encoding='utf-8')
    # Keep the tested serializer at the submission boundary. Wrapping it in another
    # object would allow an untested extra key to escape this contract.
    assert len(re.findall(r'await onSubmit\(', form)) == 1
    assert re.search(r'await onSubmit\(\s*buildRunRequest\(\{[\s\S]*?\}\)\s*\);', form)
    completed = subprocess.run(['node', 'apps/frontend/tests/campaign-payloads.js'],
                               cwd=REPO, capture_output=True, text=True, check=True)
    payloads = json.loads(completed.stdout)
    assert len(payloads) == 16
    fields = RunRequest.model_fields
    required = {key for key, field in fields.items() if field.is_required()}
    for payload in payloads:
        assert set(payload) <= fields.keys(), f'Frontend sent unknown fields: {set(payload) - fields.keys()}'
        assert required <= payload.keys()
        validated = RunRequest.model_validate(payload)
        assert validated.confirmed_facts == ['Confirmado', 'Outro fato']
        if validated.mode == 'demo':
            assert not validated.generate_image
            assert validated.model_id is None and validated.image_model_id is None
        if validated.upload:
            assert validated.product_id is None
        if validated.reference_upload:
            assert validated.reference_id is None


# ---- migration_contracts -----------------------------------------------------

def test_legacy_media_id_and_interrupted_run_remain_readable(tmp_path):
    run_id = 'run-' + 'c' * 32
    directory = tmp_path / 'campaigns/runs' / run_id
    directory.mkdir(parents=True)
    image = directory / 'feed-original.png'
    image.write_bytes(b'legacy-file')
    (directory / 'events.jsonl').write_text(json.dumps({'event': 'run_started', 'mode': 'live'}) + '\n', encoding='utf-8')
    expected = hashlib.sha256(f'campaigns/runs/{run_id}/feed-original.png'.encode()).hexdigest()[:24]
    assert media_catalog(tmp_path)[expected]['url'] == '/media/' + expected
    run = snapshot(tmp_path)[0]
    assert run['status'] == 'interrupted'
    assert run['images'][0]['id'] == expected
    assert image.read_bytes() == b'legacy-file'


def test_agent_folder_aliases_preserve_manifest_ids(tmp_path):
    assert agent_directory(tmp_path, 'creative').name == 'creative_producer'
    assert load_manifest(tmp_path, 'creative').id == 'A20'
    assert agent_directory(tmp_path, 'performance').name == 'performance_marketing'
    assert load_manifest(tmp_path, 'performance').status == 'active'
    manifest = load_manifest(tmp_path, 'creative')
    assert prompt_version(manifest, 'one', 'policy') != prompt_version(manifest, 'two', 'policy')


def test_explicit_data_path_and_static_path_are_independent(tmp_path, monkeypatch):
    monkeypatch.setenv('REALCENTER_DATA_ROOT', str(tmp_path / 'data'))
    monkeypatch.setenv('REALCENTER_STATIC_ROOT', str(tmp_path / 'web'))
    paths = AppPaths.discover()
    assert paths.data_root == tmp_path / 'data'
    assert paths.static_root == tmp_path / 'web'


def test_http_serves_configured_static_build_and_preserves_read_contracts(tmp_path, monkeypatch):
    monkeypatch.setenv('NVIDIA_API_KEY', 'nvapi-fixture')
    static = tmp_path / 'web'
    static.mkdir()
    (static / 'index.html').write_text('<html>studio</html>', encoding='utf-8')
    monkeypatch.setenv('REALCENTER_STATIC_ROOT', str(static))
    server = make_server(tmp_path / 'data', port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        assert urlopen(base + '/').read() == b'<html>studio</html>'
        config = json.load(urlopen(base + '/api/config'))
        assert set(config) == {'token', 'configured', 'model', 'image_model',
                               'models', 'image_models'}
        assert [option['id'] for option in config['image_models']] == [
            'openai:gpt-image-2', 'huggingface:Tongyi-MAI/Z-Image-Turbo',
            'huggingface:Tongyi-MAI/Z-Image', 'local:Tongyi-MAI/Z-Image-Turbo',
            'qwen:Qwen/Qwen-Image-2.1']
        nemotron = next(option for option in config['models']
                        if option['id'] == 'nvidia:nvidia/nemotron-3-ultra-550b-a55b')
        # Offered for everything, including as Director. The public shape no longer
        # carries a delegation capability because nothing asks a model to delegate.
        assert nemotron['available'] and 'delegates' not in nemotron
        assert nemotron['label'] == 'NVIDIA Nemotron 3 Ultra'
        assert nemotron['provider_label'] == 'NVIDIA'
        assert json.load(urlopen(base + '/api/runs')) == {'runs': [], 'active_id': None, 'busy': False}
        assert json.load(urlopen(base + '/api/media')) == []
        assert len(json.load(urlopen(base + '/api/formats'))) == 6
        assert json.load(urlopen(base + '/api/system/activity')) == []
        missing = 'run-' + 'f' * 32
        with pytest.raises(HTTPError) as error:
            urlopen(base + f'/api/runs/{missing}/files/diagnostics.json')
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)


# ---- brief_assistant ---------------------------------------------------------

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
    monkeypatch.setattr('studio_ai.bootstrap.settings.Settings.validate_live', lambda self: None)
    async def fail(*args, **kwargs):
        raise RuntimeError('private API response')
    monkeypatch.setattr('studio_ai.bootstrap.services.improve_brief', fail)
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
    monkeypatch.setattr('studio_ai.bootstrap.settings.Settings.validate_live', lambda self: None)
    with pytest.raises(ValueError, match='Escreva'):
        CampaignService(tmp_path).assist(AssistRequest(request='  '))
