"""Exercise the actual editor routes, write authorization and saved artifacts."""
import base64
import io
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from PIL import Image

from realcenter_marketing.presentation.http.server import make_server


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
