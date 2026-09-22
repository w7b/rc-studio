import base64
import io
import json

import pytest
from PIL import Image

from realcenter_marketing.application.commands import ReferenceEditRequest, ReferenceRequest
from realcenter_marketing.infrastructure import reference_editor
from realcenter_marketing.infrastructure.references import save_reference, reference_file, catalog


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
