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
