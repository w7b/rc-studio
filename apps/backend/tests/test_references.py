import base64
import io
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from PIL import Image

from realcenter_marketing.infrastructure import references as refs
from realcenter_marketing.presentation.http.server import make_server


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
    from realcenter_marketing.infrastructure.persistence.filesystem import media_catalog
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
    from realcenter_marketing.infrastructure.queries import LocalStudioQueries
    from realcenter_marketing.infrastructure.persistence.filesystem import media_catalog
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
    from realcenter_marketing.infrastructure.queries import LocalStudioQueries
    from realcenter_marketing.infrastructure.persistence.filesystem import media_catalog, snapshot
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
    from realcenter_marketing.infrastructure.queries import LocalStudioQueries
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
    from realcenter_marketing.infrastructure.queries import LocalStudioQueries
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
