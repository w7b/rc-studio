"""Bounded, non-destructive reference transformations and optional Qwen NIM."""
import base64
import http.client
import io
import json
import os
import threading
import time
from collections import Counter
from urllib.parse import urlsplit

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from realcenter_marketing.application.commands import ReferenceRequest
from .references import LIMIT, catalog, reference_file, save_reference
from .uploads import decode_upload

MAX_PIXELS = 25000000
RESPONSE_LIMIT = 12 * 1024 * 1024
# Fixed stripes bound memory even when many tenant contexts are created/evicted.
_locks = [threading.Lock() for _ in range(64)]


def editor_options(config=None):
    values = os.environ if config is None else config
    return {'qwen_available': bool((values.get('QWEN_IMAGE_EDIT_URL') or '').strip())}


def _png(image):
    if image.width * image.height > MAX_PIXELS:
        raise ValueError('O resultado excede 25 megapixels. Reduza o recorte ou a ampliação.')
    output = io.BytesIO()
    image.save(output, format='PNG')
    content = output.getvalue()
    if len(content) > LIMIT:
        raise ValueError('O resultado excede 8 MB. Reduza o recorte ou a ampliação.')
    return content


def _qwen(image, prompt, values):
    endpoint = (values.get('QWEN_IMAGE_EDIT_URL') or '').strip()
    if not endpoint:
        raise ValueError('Qwen-Image-Edit não está configurado neste servidor')
    url = urlsplit(endpoint)
    if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.fragment:
        raise ValueError('Configuração do endpoint Qwen-Image-Edit inválida')
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json', 'Accept-Encoding': 'identity'}
    key = (values.get('QWEN_IMAGE_EDIT_API_KEY') or '').strip()
    if key:
        headers['Authorization'] = 'Bearer ' + key
    body = json.dumps({'prompt': prompt.strip(), 'image': 'data:image/png;base64,' + base64.b64encode(_png(image)).decode(), 'seed': 0})
    connection_type = http.client.HTTPSConnection if url.scheme == 'https' else http.client.HTTPConnection
    connection = connection_type(url.hostname, url.port, timeout=120)
    deadline = time.monotonic() + 120
    try:
        path = (url.path or '/') + ('?' + url.query if url.query else '')
        connection.request('POST', path, body, headers)
        response = connection.getresponse()
        # Never follow redirects, particularly with an Authorization header.
        if response.status != 200:
            raise ValueError('O Qwen-Image-Edit não concluiu a edição. Verifique a configuração do servidor.')
        chunks, size = [], 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            if connection.sock:
                connection.sock.settimeout(remaining)
            chunk = response.read1(min(65536, RESPONSE_LIMIT + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > RESPONSE_LIMIT:
                raise ValueError('A resposta do Qwen-Image-Edit excede o limite permitido')
            chunks.append(chunk)
        payload = json.loads(b''.join(chunks))
        encoded = payload['artifacts'][0]['base64']
        if not isinstance(encoded, str) or not encoded:
            raise TypeError()
        return decode_upload(encoded)
    except (OSError, http.client.HTTPException):
        raise ValueError('Não foi possível concluir a conexão com Qwen-Image-Edit. Tente novamente.') from None
    except (KeyError, IndexError, TypeError, json.JSONDecodeError, UnicodeError):
        raise ValueError('O Qwen-Image-Edit retornou uma imagem inválida') from None
    finally:
        connection.close()


def _remove_uniform_background(image, tolerance):
    if image.width * image.height > 4000000:
        raise ValueError('Para remover fundo uniforme, use uma imagem de até 4 megapixels. Recorte primeiro.')
    result = image.convert('RGBA')
    alpha = result.getchannel('A')
    rgb = result.convert('RGB')
    w, h = rgb.size
    edges = {(x, y) for x in range(w) for y in (0, h-1)}
    edges.update((x, y) for y in range(h) for x in (0, w-1))
    opaque_edges = [rgb.getpixel(point) for point in edges if alpha.getpixel(point) == 255]
    if not opaque_edges:
        return result
    background = Counter(opaque_edges).most_common(1)[0][0]
    difference = ImageChops.difference(rgb, Image.new('RGB', rgb.size, background))
    red, green, blue = difference.split()
    distance = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    mask = distance.point(lambda value: 255 if value <= tolerance else 0)
    # Hidden RGB under transparency cannot establish or connect removable background.
    mask = ImageChops.multiply(mask, alpha.point(lambda value: 255 if value > 0 else 0))
    # Flood only similar pixels connected to an edge: holes inside the product survive.
    for x in range(w):
        for y in (0, h-1):
            if mask.getpixel((x, y)) == 255:
                ImageDraw.floodfill(mask, (x, y), 128)
    for y in range(h):
        for x in (0, w-1):
            if mask.getpixel((x, y)) == 255:
                ImageDraw.floodfill(mask, (x, y), 128)
    keep = mask.point(lambda value: 0 if value == 128 else 255)
    result.putalpha(ImageChops.multiply(alpha, keep))
    return result


def edit_reference(root, request, *, config=None):
    lock = _locks[hash(str(root.resolve())) % len(_locks)]
    if not lock.acquire(blocking=False):
        raise ValueError('Já existe uma edição de imagem em andamento. Aguarde terminar.')
    try:
        item = next((entry for entry in catalog(root) if entry['id'] == request.reference_id), None)
        if item is None:
            raise ValueError('Referência não encontrada')
        path = reference_file(root, request.reference_id)
        if path.stat().st_size > LIMIT:
            raise ValueError('A imagem excede 8 MB')
        content = decode_upload(base64.b64encode(path.read_bytes()).decode())
        with Image.open(io.BytesIO(content)) as original:
            image = ImageOps.exif_transpose(original).convert('RGBA')
        if request.operation == 'qwen':
            content = _qwen(image, request.prompt, os.environ if config is None else config)
        else:
            if request.operation == 'crop':
                crop = request.crop
                if crop.x + crop.width > image.width or crop.y + crop.height > image.height:
                    raise ValueError('O recorte ultrapassa os limites da imagem')
                image = image.crop((crop.x, crop.y, crop.x + crop.width, crop.y + crop.height))
            elif request.operation == 'enhance':
                size = image.width * request.scale, image.height * request.scale
                if size[0] * size[1] > MAX_PIXELS:
                    raise ValueError('O resultado excede 25 megapixels. Reduza a ampliação.')
                if request.scale != 1:
                    image = image.resize(size, Image.Resampling.LANCZOS)
                alpha = image.getchannel('A')
                image = image.convert('RGB').filter(ImageFilter.UnsharpMask(radius=1.5, percent=125, threshold=3)).convert('RGBA')
                image.putalpha(alpha)
            elif request.operation == 'remove_background':
                image = _remove_uniform_background(image, request.tolerance)
            content = _png(image)
        labels = {'crop': 'recorte', 'enhance': 'melhorada', 'remove_background': 'sem fundo', 'qwen': 'Qwen'}
        title = request.title.strip() or f"{item['title'][:100]} · {labels[request.operation]}"
        return save_reference(root, ReferenceRequest(kind=item['kind'], title=title, upload=base64.b64encode(content).decode()))
    finally:
        lock.release()
