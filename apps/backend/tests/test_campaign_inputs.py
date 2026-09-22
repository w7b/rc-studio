"""The IDs returned to the form must survive the real HTTP campaign flow."""
import base64
import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from realcenter_marketing.application.commands import RunRequest, ReferenceRequest
from realcenter_marketing.infrastructure.persistence.campaign_repository import FileCampaignRepository
from realcenter_marketing.infrastructure.persistence.filesystem import media_catalog
from realcenter_marketing.infrastructure.references import save_reference
from realcenter_marketing.presentation.http.server import make_server
from test_references import picture


@pytest.fixture
def http_studio(isolated_root):
    server = make_server(isolated_root, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    token = json.load(urlopen(base + '/api/config'))['token']

    def call(path, payload=None):
        request = Request(base + path, data=json.dumps(payload).encode() if payload is not None else None,
                          headers={'Content-Type': 'application/json', 'X-App-Token': token})
        with urlopen(request, timeout=15) as response:
            return response.status, json.load(response)

    try:
        yield call
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


@pytest.mark.parametrize('reference', [False, True])
@pytest.mark.parametrize('product', [False, True])
def test_demo_http_campaign_with_library_inputs(http_studio, isolated_root, reference, product):
    payload = {'request': 'Campanha pelo formulário', 'mode': 'demo', 'generate_image': False}
    content = picture()
    for enabled, kind, field in [(reference, 'feed', 'reference_id'), (product, 'product', 'product_id')]:
        if enabled:
            status, item = http_studio('/api/references', {
                'kind': kind, 'title': 'Imagem de teste', 'upload': base64.b64encode(content).decode()})
            assert status == 201
            assert item in http_studio('/api/references')[1]
            payload[field] = item['id']
    status, started = http_studio('/api/runs', payload)
    assert status == 202
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        run = next(item for item in http_studio('/api/runs')[1]['runs'] if item['id'] == started['id'])
        if run['status'] in ('completed', 'failed'):
            break
        time.sleep(.02)
    assert run['status'] == 'completed'
    assert run['outputs']['campaign']['delegation_log'] == ['social_media', 'copywriter', 'creative']
    assert run['usage']['text']['total_tokens'] == 0
    directory = isolated_root / 'campaigns/runs' / started['id']
    for present, name in [(reference, 'reference'), (product, 'product')]:
        path = directory / f'{name}.png'
        assert path.exists() is present
        if present:
            assert path.read_bytes() == content
    assert (directory / 'legenda-feed.txt').is_file()


def test_reference_id_resolves_same_bytes_as_upload(isolated_root):
    encoded = base64.b64encode(picture()).decode()
    item = save_reference(isolated_root, ReferenceRequest(kind='feed', upload=encoded))
    repository = FileCampaignRepository(isolated_root)
    assert repository.prepare_inputs(RunRequest(request='Teste', reference_id=item['id'])) == (
        repository.prepare_inputs(RunRequest(request='Teste', reference_upload=encoded)))


def test_legacy_media_id_remains_usable_as_reference(isolated_root):
    save_reference(isolated_root, ReferenceRequest(kind='product', upload=base64.b64encode(picture()).decode()))
    key = next(iter(media_catalog(isolated_root)))
    assert FileCampaignRepository(isolated_root).prepare_inputs(RunRequest(request='Teste', reference_id=key))[1] == picture()


def test_unknown_reference_is_clear_and_does_not_start_run(http_studio, isolated_root):
    with pytest.raises(HTTPError) as error:
        http_studio('/api/runs', {'request': 'Teste', 'mode': 'demo', 'reference_id': 'inexistente'})
    assert error.value.code == 400
    assert 'referência válida' in json.load(error.value)['error']
    assert not list((isolated_root / 'campaigns/runs').glob('run-*'))


@pytest.mark.parametrize('valid_id', [False, True])
def test_reference_upload_takes_precedence_even_over_invalid_id(isolated_root, valid_id):
    key = 'inexistente'
    if valid_id:
        import io
        from PIL import Image
        other = io.BytesIO()
        Image.new('RGB', (20, 20), 'blue').save(other, format='PNG')
        key = save_reference(isolated_root, ReferenceRequest(
            kind='feed', upload=base64.b64encode(other.getvalue()).decode()))['id']
    request = RunRequest(request='Teste', reference_upload=base64.b64encode(picture()).decode(),
                         reference_id=key)
    assert FileCampaignRepository(isolated_root).prepare_inputs(request)[1] == picture()


def test_library_ids_do_not_cross_tenants(isolated_root, tmp_path):
    item = save_reference(tmp_path / 'other', ReferenceRequest(kind='feed', upload=base64.b64encode(picture()).decode()))
    with pytest.raises(ValueError, match='referência válida'):
        FileCampaignRepository(isolated_root).prepare_inputs(RunRequest(request='Teste', reference_id=item['id']))


def test_visual_reference_cannot_be_used_as_product(isolated_root):
    item = save_reference(isolated_root, ReferenceRequest(kind='feed', upload=base64.b64encode(picture()).decode()))
    with pytest.raises(ValueError, match='foto válida'):
        FileCampaignRepository(isolated_root).prepare_inputs(RunRequest(request='Teste', product_id=item['id']))
