"""Referências visuais e o editor de referências."""
import base64
import io
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import pytest
from PIL import Image
from studio_ai.infrastructure import references as refs
from studio_ai.presentation.http.server import make_server
from studio_ai.application.commands import ReferenceEditRequest, ReferenceRequest
from studio_ai.infrastructure import reference_editor
from studio_ai.infrastructure.references import save_reference, reference_file, catalog


# ---- references --------------------------------------------------------------

def picture(width=640):
    output = io.BytesIO()
    Image.new('RGB', (width, 360), 'orange').save(output, 'PNG')
    return output.getvalue()


@pytest.mark.parametrize('url', ['https://youtu.be/abcdefghijk', 'https://www.youtube.com/watch?v=abcdefghijk&t=2', 'https://youtube.com/shorts/abcdefghijk', 'https://m.youtube.com/live/abcdefghijk'])
def test_youtube_urls(url):
    assert refs.youtube_id(url) == 'abcdefghijk'


@pytest.mark.parametrize('url', ['https://youtube.com.evil.test/watch?v=abcdefghijk', 'https://youtu.be/../../etc/passwd', 'https://youtube.com/watch?v=bad'])
def test_invalid_youtube_urls(url):
    with pytest.raises(ValueError):
        refs.youtube_id(url)


def test_thumbnail_fallback(monkeypatch):
    calls = []
    def fetch(url, deadline=None):
        calls.append(url)
        return picture(120 if len(calls) == 1 else 640)
    monkeypatch.setattr(refs, 'fetch', fetch)
    content, source = refs.import_image(refs.ReferenceRequest(kind='youtube', url='https://youtu.be/abcdefghijk'))
    assert content == picture()
    assert calls[-1].endswith('/sddefault.jpg')
    assert source == 'https://www.youtube.com/watch?v=abcdefghijk'


def test_uploaded_product_is_in_brand_kit_library_and_can_be_reused(tmp_path):
    from studio_ai.infrastructure.persistence.filesystem import media_catalog
    request = refs.ReferenceRequest(kind='product', title='Café 500 g', upload=base64.b64encode(picture()).decode())
    saved = refs.save_reference(tmp_path, request)
    assert refs.save_reference(tmp_path, request) == saved
    path = refs.reference_file(tmp_path, saved['id'])
    assert path.is_relative_to(tmp_path / 'brand/products')
    assert path.read_bytes() == picture()
    products = [entry for entry in media_catalog(tmp_path).values() if entry['product']]
    assert len(products) == 1
    assert products[0]['title'] == 'Café 500 g'
    assert products[0]['path'] == path
    assert refs.catalog(tmp_path / 'other-store') == []
    assert media_catalog(tmp_path / 'other-store') == {}


def test_product_type_requires_a_real_uploaded_image(tmp_path, monkeypatch):
    monkeypatch.setattr(refs, 'fetch', lambda *args: pytest.fail('Product uploads must not fetch URLs'))
    with pytest.raises(ValueError, match='Envie um arquivo'):
        refs.save_reference(tmp_path, refs.ReferenceRequest(kind='product', url='https://example.test/photo.png'))
    with pytest.raises(ValueError):
        refs.save_reference(tmp_path, refs.ReferenceRequest(kind='product', upload=base64.b64encode(b'not an image').decode()))
    assert not (tmp_path / 'brand/products').exists()


@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', '::ffff:127.0.0.1'])
def test_private_dns_is_rejected(monkeypatch, address):
    monkeypatch.setattr(refs.socket, 'getaddrinfo', lambda *a, **k: [(2, 1, 6, '', (address, 443))])
    with pytest.raises(ValueError, match='público'):
        refs.public_address('untrusted.example')


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'http://example.com/image.png', 'https://user:pass@example.com/a', 'https://example.com:8443/a'])
def test_unsafe_urls(url):
    with pytest.raises(ValueError):
        refs.fetch(url)


def test_instagram_preview_and_story_fallback(monkeypatch):
    calls = []
    def fetch(url, deadline=None):
        calls.append(url)
        return b'<meta property="og:image" content="https://cdn.example/image.png?a=1&amp;b=2">' if len(calls) == 1 else picture()
    monkeypatch.setattr(refs, 'fetch', fetch)
    assert refs.import_image(refs.ReferenceRequest(url='https://www.instagram.com/p/abc/'))[0] == picture()
    assert calls[1] == 'https://cdn.example/image.png?a=1&b=2'
    with pytest.raises(ValueError, match='Stories'):
        refs.import_image(refs.ReferenceRequest(kind='story', url='https://www.instagram.com/stories/person/123/'))


def test_direct_link_rejects_html(monkeypatch):
    monkeypatch.setattr(refs, 'fetch', lambda *a: b'<html>not an image</html>')
    with pytest.raises(ValueError, match='PNG'):
        refs.import_image(refs.ReferenceRequest(url='https://example.com/page'))


def test_library_http_persistence_download_and_guards(tmp_path):
    server = make_server(tmp_path, 0, host='0.0.0.0')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        token = json.load(urlopen(base + '/api/config'))['token']
        data = json.dumps({'title': 'Minha referência', 'kind': 'story', 'upload': base64.b64encode(picture()).decode()}).encode()
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + '/api/references', data=data, headers={'Content-Type': 'application/json'}))
        assert error.value.code == 403
        headers = {'Content-Type': 'application/json', 'X-App-Token': token}
        item = json.load(urlopen(Request(base + '/api/references', data=data, headers=headers)))
        duplicate = json.load(urlopen(Request(base + '/api/references', data=data, headers=headers)))
        assert item == duplicate
        assert len(refs.catalog(tmp_path)) == 1
        assert json.load(urlopen(base + '/api/references'))[0]['width'] == 640
        assert urlopen(base + item['url']).read() == picture()
        response = urlopen(base + f"/api/references/{item['id']}/download")
        assert response.headers['Content-Disposition'].startswith('attachment;')
        assert response.read() == picture()
        with pytest.raises(HTTPError) as error:
            urlopen(base + '/api/references/unknown/image')
        assert error.value.code == 404
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + '/api/references', headers={'Host': f'evil.test:{server.server_port}'}))
        assert error.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


@pytest.mark.parametrize('kind,endpoint', [('feed', 'references'), ('product', 'references'), ('product', 'media')])
def test_delete_library_image_moves_image_and_metadata_to_trash(tmp_path, kind, endpoint):
    from studio_ai.infrastructure.queries import LocalStudioQueries
    from studio_ai.infrastructure.persistence.filesystem import media_catalog
    saved = refs.save_reference(tmp_path, refs.ReferenceRequest(kind=kind, title='Imagem', upload=base64.b64encode(picture()).decode()))
    image = refs.reference_file(tmp_path, saved['id'])
    copied_input = tmp_path / 'campaigns/runs' / ('run-' + '1' * 32) / 'product.png'
    copied_input.parent.mkdir(parents=True)
    copied_input.write_bytes(picture())
    key = saved['id'] if endpoint == 'references' else next(key for key, item in media_catalog(tmp_path).items() if item['product'])
    LocalStudioQueries(tmp_path).delete_image(key, endpoint)
    assert not image.exists()
    assert refs.catalog(tmp_path) == []
    assert not [item for item in media_catalog(tmp_path).values() if item['product']]
    assert copied_input.read_bytes() == picture()
    assert next((tmp_path / '.trash/library').rglob(image.name)).read_bytes() == picture()
    assert next((tmp_path / '.trash/library').rglob(saved['id'] + '.json')).is_file()
    with pytest.raises(ValueError):
        LocalStudioQueries(tmp_path).delete_image(key, endpoint)


def test_delete_artwork_preserves_campaign_and_rejects_input_or_unknown_ids(tmp_path):
    from studio_ai.infrastructure.queries import LocalStudioQueries
    from studio_ai.infrastructure.persistence.filesystem import media_catalog, snapshot
    directory = tmp_path / 'campaigns/runs' / ('run-' + '2' * 32)
    directory.mkdir(parents=True)
    (directory / 'feed-1.png').write_bytes(picture())
    (directory / 'product.png').write_bytes(picture())
    (directory / 'brief.json').write_text('{"request":"Manter campanha"}', encoding='utf-8')
    catalog = {item['name']: key for key, item in media_catalog(tmp_path).items()}
    assert len(snapshot(tmp_path)[0]['images']) == 1
    queries = LocalStudioQueries(tmp_path)
    for key in ('../outside', 'unknown', catalog['product.png']):
        with pytest.raises(ValueError):
            queries.delete_image(key, 'media')
    queries.delete_image(catalog['feed-1.png'], 'media')
    assert snapshot(tmp_path)[0]['images'] == []
    assert (directory / 'brief.json').is_file()
    assert (directory / 'product.png').is_file()


def test_delete_reference_rolls_back_if_metadata_cannot_move(tmp_path, monkeypatch):
    from pathlib import Path
    from studio_ai.infrastructure.queries import LocalStudioQueries
    saved = refs.save_reference(tmp_path, refs.ReferenceRequest(upload=base64.b64encode(picture()).decode()))
    image = refs.reference_file(tmp_path, saved['id'])
    metadata = tmp_path / 'campaigns/references' / (saved['id'] + '.json')
    rename = Path.rename
    def fail_metadata(path, target):
        if path == metadata:
            raise OSError('fixture failure')
        return rename(path, target)
    monkeypatch.setattr(Path, 'rename', fail_metadata)
    with pytest.raises(ValueError, match='Não foi possível apagar'):
        LocalStudioQueries(tmp_path).delete_image(saved['id'], 'references')
    assert image.read_bytes() == picture()
    assert len(refs.catalog(tmp_path)) == 1


def test_delete_refuses_trash_outside_store(tmp_path):
    from studio_ai.infrastructure.queries import LocalStudioQueries
    root = tmp_path / 'store'
    saved = refs.save_reference(root, refs.ReferenceRequest(upload=base64.b64encode(picture()).decode()))
    outside = tmp_path / 'other-store'
    outside.mkdir()
    try:
        (root / '.trash').symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Symlink privilege unavailable')
    with pytest.raises(ValueError):
        LocalStudioQueries(root).delete_image(saved['id'], 'references')
    assert refs.reference_file(root, saved['id']).is_file()
    assert list(outside.iterdir()) == []


def test_delete_image_http_refuses_busy_store_and_recovers(tmp_path):
    server = make_server(tmp_path, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    saved = refs.save_reference(tmp_path, refs.ReferenceRequest(upload=base64.b64encode(picture()).decode()))
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        token = json.load(urlopen(base + '/api/config'))['token']
        headers = {'Content-Type': 'application/json', 'X-App-Token': token}
        request = Request(base + f'/api/references/{saved["id"]}/delete', data=b'{}', headers=headers)
        scheduler = server.container.service.scheduler
        assert scheduler.acquire()
        try:
            with pytest.raises(HTTPError) as error:
                urlopen(request)
            assert error.value.code == 409
            assert refs.reference_file(tmp_path, saved['id']).is_file()
        finally:
            scheduler.release()
        assert json.load(urlopen(request))['deleted'] == saved['id']
        assert refs.catalog(tmp_path) == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


# ---- reference_editor --------------------------------------------------------

def source(root):
    image = Image.new('RGBA', (12, 10), 'white')
    for x in range(3, 9):
        for y in range(3, 7):
            image.putpixel((x, y), (180, 20, 30, 255))
    image.putpixel((5, 5), (180, 20, 30, 100))
    output = io.BytesIO()
    image.save(output, format='PNG')
    return save_reference(root, ReferenceRequest(kind='product', upload=base64.b64encode(output.getvalue()).decode()))


def test_crop_preserves_original_and_alpha(tmp_path):
    item = source(tmp_path)
    original = reference_file(tmp_path, item['id']).read_bytes()
    result = reference_editor.edit_reference(tmp_path, ReferenceEditRequest(reference_id=item['id'], operation='crop', crop={'x': 3, 'y': 3, 'width': 6, 'height': 4}))
    assert result['kind'] == 'product'
    assert (result['width'], result['height']) == (6, 4)
    with Image.open(reference_file(tmp_path, result['id'])) as image:
        assert image.getpixel((2, 2))[3] == 100
    assert reference_file(tmp_path, item['id']).read_bytes() == original
    assert len(catalog(tmp_path)) == 2


def test_crop_rejects_bounds_and_missing_reference(tmp_path):
    item = source(tmp_path)
    with pytest.raises(ValueError, match='limites'):
        reference_editor.edit_reference(tmp_path, ReferenceEditRequest(reference_id=item['id'], operation='crop', crop={'x': 10, 'y': 0, 'width': 3, 'height': 3}))
    with pytest.raises(ValueError, match='encontrada'):
        reference_editor.edit_reference(tmp_path / 'other-tenant', ReferenceEditRequest(reference_id=item['id'], operation='enhance'))


def test_enhance_upscales_and_keeps_alpha(tmp_path):
    item = source(tmp_path)
    result = reference_editor.edit_reference(tmp_path, ReferenceEditRequest(reference_id=item['id'], operation='enhance', scale=2))
    with Image.open(reference_file(tmp_path, result['id'])) as image:
        assert image.size == (24, 20)
        assert image.mode == 'RGBA'
        assert image.getextrema()[3][0] < 255


def test_uniform_background_becomes_transparent(tmp_path):
    item = source(tmp_path)
    result = reference_editor.edit_reference(tmp_path, ReferenceEditRequest(reference_id=item['id'], operation='remove_background'))
    with Image.open(reference_file(tmp_path, result['id'])) as image:
        assert image.getpixel((0, 0))[3] == 0
        assert image.getpixel((4, 4))[3] == 255
        assert image.getpixel((5, 5))[3] == 100


def test_existing_transparent_background_does_not_erase_black_product():
    image = Image.new('RGBA', (10, 10), (0, 0, 0, 0))
    for x in range(3, 7):
        for y in range(3, 7):
            image.putpixel((x, y), (0, 0, 0, 255))
    result = reference_editor._remove_uniform_background(image, 25)
    assert result.tobytes() == image.tobytes()


def test_transparent_pixels_do_not_connect_opaque_background_to_product():
    image = Image.new('RGBA', (10, 10), (0, 0, 0, 0))
    for x in range(10):
        image.putpixel((x, 0), (0, 0, 0, 255))
    for x in range(3, 7):
        for y in range(3, 7):
            image.putpixel((x, y), (0, 0, 0, 255))
    result = reference_editor._remove_uniform_background(image, 25)
    assert result.getpixel((5, 0))[3] == 0
    assert result.getpixel((5, 5))[3] == 255


def test_qwen_requires_configuration_and_prompt(tmp_path):
    item = source(tmp_path)
    with pytest.raises(ValueError, match='configurado'):
        reference_editor.edit_reference(tmp_path, ReferenceEditRequest(reference_id=item['id'], operation='qwen', prompt='Improve'), config={})
    with pytest.raises(ValueError):
        ReferenceEditRequest(reference_id=item['id'], operation='qwen', prompt=' ')


def test_options_do_not_expose_config():
    assert reference_editor.editor_options({'QWEN_IMAGE_EDIT_URL': 'http://localhost:8000/v1/infer', 'QWEN_IMAGE_EDIT_API_KEY': 'secret'}) == {'qwen_available': True}
    assert reference_editor.editor_options({}) == {'qwen_available': False}


def test_qwen_transport_payload_and_saved_output(tmp_path, monkeypatch):
    item = source(tmp_path)
    output = io.BytesIO()
    Image.new('RGB', (4, 6), 'blue').save(output, format='PNG')
    returned = json.dumps({'artifacts': [{'base64': base64.b64encode(output.getvalue()).decode()}]}).encode()
    calls = []

    class Connection:
        sock = None
        def __init__(self, host, port, timeout):
            calls.append((host, port, timeout))
        def request(self, method, path, body, headers):
            calls.append((method, path, json.loads(body), headers))
        def getresponse(self):
            response = io.BytesIO(returned)
            response.status = 200
            return response
        def close(self):
            calls.append('closed')

    monkeypatch.setattr(reference_editor.http.client, 'HTTPConnection', Connection)
    result = reference_editor.edit_reference(tmp_path, ReferenceEditRequest(reference_id=item['id'], operation='qwen', prompt='Isolate product'), config={'QWEN_IMAGE_EDIT_URL': 'http://model:8000/v1/infer', 'QWEN_IMAGE_EDIT_API_KEY': 'private'})
    assert (result['width'], result['height']) == (4, 6)
    assert calls[0] == ('model', 8000, 120)
    assert calls[1][0:2] == ('POST', '/v1/infer')
    assert calls[1][2]['image'].startswith('data:image/png;base64,')
    assert calls[1][2]['prompt'] == 'Isolate product'
    assert calls[1][3]['Authorization'] == 'Bearer private'
    assert calls[-1] == 'closed'


def test_qwen_redirect_is_rejected_without_forwarding_key(tmp_path, monkeypatch):
    item = source(tmp_path)
    calls = []

    class Connection:
        def __init__(self, *args, **kwargs):
            pass
        def request(self, *args):
            calls.append(args)
        def getresponse(self):
            response = io.BytesIO(b'private response with secret')
            response.status = 302
            return response
        def close(self):
            pass

    monkeypatch.setattr(reference_editor.http.client, 'HTTPConnection', Connection)
    with pytest.raises(ValueError, match='não concluiu') as error:
        reference_editor.edit_reference(tmp_path, ReferenceEditRequest(reference_id=item['id'], operation='qwen', prompt='Edit'), config={'QWEN_IMAGE_EDIT_URL': 'http://model:8000/v1/infer', 'QWEN_IMAGE_EDIT_API_KEY': 'private'})
    assert len(calls) == 1
    assert 'private' not in str(error.value)


@pytest.mark.parametrize('payload', [b'{"artifacts":[{"base64":""}]}', b'{}', b'not-json'])
def test_qwen_malformed_response_is_safe(tmp_path, monkeypatch, payload):
    item = source(tmp_path)

    class Connection:
        sock = None
        def __init__(self, *args, **kwargs):
            pass
        def request(self, *args):
            pass
        def getresponse(self):
            response = io.BytesIO(payload)
            response.status = 200
            return response
        def close(self):
            pass

    monkeypatch.setattr(reference_editor.http.client, 'HTTPConnection', Connection)
    with pytest.raises(ValueError, match='imagem inválida'):
        reference_editor.edit_reference(tmp_path, ReferenceEditRequest(reference_id=item['id'], operation='qwen', prompt='Edit'), config={'QWEN_IMAGE_EDIT_URL': 'http://model:8000/v1/infer'})
    assert len(catalog(tmp_path)) == 1


def test_busy_edit_does_not_mutate_library(tmp_path):
    item = source(tmp_path)
    lock = reference_editor._locks[hash(str(tmp_path.resolve())) % len(reference_editor._locks)]
    with lock, pytest.raises(ValueError, match='andamento'):
        reference_editor.edit_reference(tmp_path, ReferenceEditRequest(reference_id=item['id'], operation='enhance'))
    assert len(catalog(tmp_path)) == 1


def test_bounds_for_output_and_background_removal(tmp_path, monkeypatch):
    item = source(tmp_path)
    monkeypatch.setattr(reference_editor, 'MAX_PIXELS', 200)
    with pytest.raises(ValueError, match='megapixels'):
        reference_editor.edit_reference(tmp_path, ReferenceEditRequest(reference_id=item['id'], operation='enhance', scale=2))
    with pytest.raises(ValueError, match='4 megapixels'):
        reference_editor._remove_uniform_background(Image.new('RGBA', (2001, 2000)), 25)
    monkeypatch.setattr(reference_editor, 'LIMIT', 1)
    with pytest.raises(ValueError, match='8 MB'):
        reference_editor._png(Image.new('RGBA', (2, 2)))


def test_rotated_jpeg_catalog_and_crop_use_display_coordinates(tmp_path):
    image = Image.new('RGB', (12, 8), 'red')
    exif = image.getexif()
    exif[274] = 6
    output = io.BytesIO()
    image.save(output, format='JPEG', exif=exif)
    item = save_reference(tmp_path, ReferenceRequest(upload=base64.b64encode(output.getvalue()).decode()))
    assert (item['width'], item['height']) == (8, 12)
    # Existing library metadata written before orientation handling must also normalize.
    metadata = tmp_path / 'campaigns/references' / (item['id'] + '.json')
    legacy = json.loads(metadata.read_text())
    legacy.update(width=12, height=8)
    metadata.write_text(json.dumps(legacy))
    listed = catalog(tmp_path)[0]
    assert (listed['width'], listed['height']) == (8, 12)
    result = reference_editor.edit_reference(tmp_path, ReferenceEditRequest(reference_id=item['id'], operation='crop', crop={'x': 0, 'y': 8, 'width': 8, 'height': 4}))
    assert (result['width'], result['height']) == (8, 4)


# ---- reference_editor_http ---------------------------------------------------

def test_editor_http_requires_token_and_preserves_source(tmp_path):
    server = make_server(tmp_path, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        token = json.load(urlopen(base + '/api/config'))['token']
        options = json.load(urlopen(base + '/api/references/editor-options'))
        assert isinstance(options['qwen_available'], bool)
        assert 'key' not in json.dumps(options).lower()
        stream = io.BytesIO()
        Image.new('RGBA', (40, 30), (240, 120, 60, 128)).save(stream, 'PNG')

        def post(path, body, authorized=True):
            headers = {'Content-Type': 'application/json'}
            if authorized:
                headers['X-App-Token'] = token
            return json.load(urlopen(Request(base + path, data=json.dumps(body).encode(), headers=headers)))

        original = post('/api/references', {
            'kind': 'product', 'title': 'Produto original',
            'upload': base64.b64encode(stream.getvalue()).decode(),
        })
        payload = {'reference_id': original['id'], 'operation': 'crop',
                   'crop': {'x': 5, 'y': 5, 'width': 20, 'height': 10}}
        with pytest.raises(HTTPError) as error:
            post('/api/references/edit', payload, authorized=False)
        assert error.value.code == 403
        edited = post('/api/references/edit', payload)
        assert (edited['width'], edited['height'], edited['kind']) == (20, 10, 'product')
        assert edited['id'] != original['id']
        assert urlopen(base + original['url']).read() == stream.getvalue()
        assert len(json.load(urlopen(base + '/api/references'))) == 2
        with Image.open(io.BytesIO(urlopen(base + edited['url']).read())) as image:
            assert image.getpixel((0, 0))[3] == 128
        payload['reference_id'] = 'a' * 32
        with pytest.raises(HTTPError) as error:
            post('/api/references/edit', payload)
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
