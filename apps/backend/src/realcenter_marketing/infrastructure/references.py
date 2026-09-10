from realcenter_marketing.application.commands import ReferenceRequest
"""Local reference library and bounded public-image imports."""
import base64
import hashlib
import http.client
import io
import ipaddress
import json
import re
import socket
import ssl
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from realcenter_marketing.infrastructure.persistence.filesystem import read_json
from realcenter_marketing.infrastructure.uploads import decode_upload

LIMIT = 8 * 1024 * 1024
KEY = re.compile(r'[a-f0-9]{32}\Z')




def public_address(host):
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('O endereço precisa ser público')
    return addresses[0][4][0]


def fetch(url, deadline=None):
    """Pin validated DNS address; verify TLS hostname; validate every redirect."""
    deadline = deadline or time.monotonic() + 25
    for _ in range(4):
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError('Use um link HTTPS público, sem credenciais ou porta especial')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('A origem demorou para responder. Tente novamente ou envie a imagem.')
        address = public_address(parsed.hostname)
        connection = http.client.HTTPSConnection(parsed.hostname, timeout=min(8, remaining))
        try:
            raw = socket.create_connection((address, 443), timeout=min(8, remaining))
            try:
                connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=parsed.hostname)
            except Exception:
                raw.close()
                raise
            connection.request('GET', parsed.path + ('?' + parsed.query if parsed.query else ''), headers={'User-Agent': 'RealCenterStudio/1.0', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                url = urljoin(url, response.getheader('Location', ''))
                continue
            if response.status != 200:
                raise ValueError('A origem não disponibilizou a imagem. Envie o arquivo manualmente.')
            chunks, size = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError('A origem demorou para responder. Envie o arquivo manualmente.')
                if connection.sock:
                    connection.sock.settimeout(min(8, remaining))
                chunk = response.read1(min(65536, LIMIT + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > LIMIT:
                    raise ValueError('A imagem excede 8 MB')
            return b''.join(chunks)
        except (OSError, http.client.HTTPException):
            raise ValueError('Não foi possível acessar a origem. Tente novamente ou envie a imagem.') from None
        finally:
            connection.close()
    raise ValueError('A origem redirecionou muitas vezes')


def youtube_id(url):
    parsed = urlsplit(url)
    host = parsed.hostname
    parts = parsed.path.strip('/').split('/')
    video = None
    if host == 'youtu.be' and len(parts) == 1:
        video = parts[0]
    elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
        if parsed.path == '/watch':
            video = parse_qs(parsed.query).get('v', [''])[0]
        elif len(parts) == 2 and parts[0] in ('shorts', 'embed', 'live'):
            video = parts[1]
    if not video or not re.fullmatch(r'[A-Za-z0-9_-]{11}', video):
        raise ValueError('Cole um link válido de vídeo do YouTube')
    return video


class PreviewParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.image = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and attrs.get('property') == 'og:image':
            self.image = attrs.get('content')


def import_image(request):
    if request.upload:
        return decode_upload(request.upload), ''
    url = request.url.strip()
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Cole um link HTTPS público')
    if request.kind == 'youtube':
        video = youtube_id(url)
        deadline = time.monotonic() + 25
        for size in ('maxresdefault', 'sddefault', 'hqdefault'):
            try:
                content = fetch(f'https://i.ytimg.com/vi/{video}/{size}.jpg', deadline)
                decode_upload(base64.b64encode(content).decode())
                with Image.open(io.BytesIO(content)) as img:
                    if img.width < 320:
                        continue
                return content, f'https://www.youtube.com/watch?v={video}'
            except ValueError:
                continue
        raise ValueError('Thumbnail indisponível. Confira se o vídeo é público ou envie a imagem.')
    if parsed.hostname in ('instagram.com', 'www.instagram.com'):
        if parsed.path.startswith('/stories/'):
            raise ValueError('Stories por link exigem uma sessão do Instagram. Salve a imagem e use Enviar arquivo.')
        if not re.fullmatch(r'/(p|reel)/[A-Za-z0-9_-]+/?', parsed.path):
            raise ValueError('Cole o link de uma publicação do Instagram')
        url = 'https://www.instagram.com' + parsed.path
        parser = PreviewParser()
        parser.feed(fetch(url).decode('utf-8', errors='replace'))
        if not parser.image:
            raise ValueError('O Instagram não liberou a prévia pública. Use Enviar arquivo.')
        content = fetch(urljoin(url, parser.image))
    else:
        content = fetch(url)
    decode_upload(base64.b64encode(content).decode())
    return content, url


def catalog(root):
    directory = root / 'campaigns' / 'references'
    result = []
    for path in directory.glob('*.json'):
        item = read_json(path)
        if not KEY.fullmatch(path.stem) or not isinstance(item, dict):
            continue
        if item.get('id') != path.stem or item.get('extension') not in ('png', 'jpg'):
            continue
        image = directory / (path.stem + '.' + item['extension'])
        if image.is_file() and image.resolve().is_relative_to(directory.resolve()):
            result.append(item)
    return sorted(result, key=lambda item: item['created_at'], reverse=True)


def save_reference(root, request):
    content, source = import_image(request)
    with Image.open(io.BytesIO(content)) as image:
        width, height = image.size
        extension = 'png' if image.format == 'PNG' else 'jpg'
    key = hashlib.sha256(content + request.kind.encode()).hexdigest()[:32]
    directory = root / 'campaigns' / 'references'
    directory.mkdir(parents=True, exist_ok=True)
    existing = next((item for item in catalog(root) if item['id'] == key), None)
    if existing:
        return existing
    item = dict(id=key, title=request.title.strip() or f'Referência {request.kind}', kind=request.kind,
                source=source, extension=extension, width=width, height=height,
                created_at=datetime.now(timezone.utc).isoformat(), url=f'/api/references/{key}/image')
    (directory / f'{key}.{extension}').write_bytes(content)
    # Atomic metadata publication keeps concurrent listing from seeing partial JSON.
    import uuid
    temporary = directory / f'.{key}-{uuid.uuid4().hex}.tmp'
    temporary.write_text(json.dumps(item, ensure_ascii=False), encoding='utf-8')
    temporary.replace(directory / f'{key}.json')
    return item


def reference_file(root, key):
    item = next((item for item in catalog(root) if item['id'] == key), None)
    if item is None:
        raise ValueError('Referência não encontrada')
    return root / 'campaigns' / 'references' / f"{key}.{item['extension']}"
