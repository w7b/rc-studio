"""Exercise the real NGINX config against a disposable, offline shared app.

Build the app image and pull nginx:stable-alpine first. Only uniquely named test
containers are removed; no Compose volumes or existing services are touched.
"""
import argparse
import base64
import binascii
import http.client
import json
import re
import socket
import struct
import subprocess
import time
import uuid
import zlib
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def docker(*arguments, check=True):
    result = subprocess.run(['docker', *arguments], capture_output=True, text=True, check=check)
    return result.stdout.strip()


def png():
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', binascii.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\xff\x80\x00')) + chunk(b'IEND', b''))


def verify(base):
    def request(path, data=None, headers=None, expected=200):
        payload = json.dumps(data).encode() if data is not None else None
        try:
            response = urlopen(Request(base + path, data=payload, headers={
                'Content-Type': 'application/json', 'Origin': base, **(headers or {})}), timeout=20)
        except HTTPError as failure:
            response = failure
        with response:
            body = response.read()
            assert response.status == expected, (path, response.status, body[:200])
            return body, response.headers

    html, _ = request('/studio/account')
    for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html.decode()):
        request(asset)
    assert b'/assets/' in html
    assert json.loads(request('/api/config')[0])['shared'] is True
    request('/api/runs', expected=401)
    request('/assets/absent.js', expected=404)
    login, headers = request('/api/login', {'email': 'proxy@example.test', 'password': 'senha-de-teste-proxy'})
    assert 'HttpOnly' in headers['Set-Cookie'] and 'SameSite=Lax' in headers['Set-Cookie']
    jar = SimpleCookie(headers['Set-Cookie'])
    auth = {'Cookie': f'rcs_session={jar["rcs_session"].value}', 'X-App-Token': json.loads(login)['csrf']}
    session = json.loads(request('/api/session', headers=auth)[0])
    assert session['authenticated'] is True
    request('/api/store', {'brand_name': 'Teste'}, headers={**auth, 'Origin': 'https://evil.example'}, expected=403)
    request('/api/store', {'brand_name': 'Teste'}, headers={'Cookie': auth['Cookie']}, expected=403)
    request('/api/config', headers={'Host': 'evil.example'}, expected=403)
    request('/api/store', {'brand_name': 'Teste'}, headers=auth)
    # A valid image padded to exactly 8 MiB verifies the entire base64 upload path.
    picture = png().ljust(8 * 1024 * 1024, b'\x00')
    uploaded = json.loads(request('/api/references', {
        'title': 'Produto teste', 'kind': 'product',
        'upload': base64.b64encode(picture).decode(),
    }, headers=auth, expected=201)[0])
    media = json.loads(request('/api/media', headers=auth)[0])
    products = [item for item in media if item['product']]
    assert products, media
    assert uploaded['id']
    request(products[0]['url'], headers=auth)
    # Reject an oversized body at the edge without transmitting or logging it.
    connection = http.client.HTTPConnection('127.0.0.1', int(base.rsplit(':', 1)[1]), timeout=10)
    try:
        connection.putrequest('POST', '/api/references')
        connection.putheader('Content-Length', str(24 * 1024 * 1024))
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == 413
        assert 'error' in json.loads(response.read())
    finally:
        connection.close()
    run = json.loads(request('/api/runs', {'request': 'Campanha sintética', 'mode': 'demo'}, headers=auth, expected=202)[0])
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        runs = json.loads(request('/api/runs', headers=auth)[0])
        if not runs['active_id']:
            break
        time.sleep(.2)
    assert runs['runs'][0]['status'] == 'completed', runs
    request(f'/api/runs/{run["id"]}/files/legenda-feed.txt', headers=auth)
    request('/api/logout', {}, headers=auth)
    request('/api/runs', headers=auth, expected=401)
    # User-supplied IP headers cannot evade the real client's attempt budget.
    # The successful login above already consumed one of the 20 attempts.
    for index in range(20):
        request('/api/login', {'email': f'fake{index}@example.test', 'password': 'wrong'},
                headers={'X-Real-IP': f'203.0.113.{index + 1}', 'X-Forwarded-For': f'203.0.113.{index + 1}'},
                expected=429 if index == 19 else 401)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='studio-ai:test')
    parser.add_argument('--postgres', action='store_true', help='Usar PostgreSQL descartável e o schema do pacote instalado')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    name = 'studio-nginx-test-' + uuid.uuid4().hex[:10]
    backend, proxy, database = name + '-app', name + '-proxy', name + '-db'
    worker, volume = name + '-worker', name + '-data'
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    # Docker Desktop does not publish ports for an internal-only bridge. This
    # dedicated bridge exposes only the proxy on loopback; all requests use demo.
    docker('network', 'create', name)
    try:
        database_environment = []
        data_mount = []
        if args.postgres:
            docker('run', '-d', '--name', database, '--network', name, '--network-alias', 'db',
                   '-e', 'POSTGRES_USER=studio', '-e', 'POSTGRES_DB=studio',
                   '-e', 'POSTGRES_PASSWORD=fixture-only', 'postgres:17-alpine')
            deadline = time.monotonic() + 35
            while True:
                ready = subprocess.run(['docker', 'exec', database, 'pg_isready', '-U', 'studio', '-d', 'studio'],
                                       capture_output=True).returncode == 0
                if ready:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('Banco descartável não iniciou')
                time.sleep(.5)
            database_environment = ['-e', 'SMOKE_POSTGRES=1', '-e', 'REALCENTER_DEPLOYMENT_MODE=shared',
                                    '-e', 'PGHOST=db', '-e', 'PGPORT=5432', '-e', 'PGDATABASE=studio',
                                    '-e', 'PGUSER=studio', '-e', 'PGPASSWORD=fixture-only']
            docker('volume', 'create', volume)
            data_mount = ['--mount', f'type=volume,source={volume},target=/app/data',
                          '-e', 'SMOKE_DATA_ROOT=/app/data']
        docker('run', '-d', '--name', backend, '--network', name, '--network-alias', 'studio',
               '-e', f'REALCENTER_PUBLIC_HOST=127.0.0.1:{port}', '-e', 'REALCENTER_ENV_ROOT=/tmp/platform',
               '-e', 'REALCENTER_TRUSTED_PROXIES=nginx',
               '--mount', f'type=bind,source={root / "apps/backend/tests"},target=/tmp/tests,readonly',
               *database_environment, *data_mount, args.image, 'python', '/tmp/tests/nginx_fixture.py')
        if args.postgres:
            docker('run', '-d', '--name', worker, '--network', name,
                   '-e', 'REALCENTER_ENV_ROOT=/tmp/platform', *database_environment, *data_mount,
                   '--health-cmd', 'python scripts/worker.py --healthcheck',
                   args.image, 'python', 'scripts/worker.py')
        docker('run', '-d', '--name', proxy, '--network', name, '--network-alias', 'nginx', '-p', f'127.0.0.1:{port}:8080',
               '--read-only', '--tmpfs', '/etc/nginx/conf.d', '--tmpfs', '/var/cache/nginx', '--tmpfs', '/var/run',
               '-e', 'NGINX_UPSTREAM=studio:8765', '-e', 'NGINX_ENVSUBST_FILTER=^NGINX_UPSTREAM$',
               '--mount', f'type=bind,source={root / "deploy/nginx/templates"},target=/etc/nginx/templates,readonly',
               '--mount', f'type=bind,source={root / "deploy/nginx/snippets"},target=/etc/nginx/snippets,readonly',
               'nginx:stable-alpine')
        deadline = time.monotonic() + 40
        while True:
            try:
                with urlopen(base + '/api/config', timeout=2) as response:
                    assert response.status == 200
                break
            except (URLError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.5)
        docker('exec', proxy, 'nginx', '-t')
        docker('exec', proxy, 'wget', '-q', '--header=Host: localhost:8765', '-O', '/dev/null',
               'http://127.0.0.1:8080/api/config')
        verify(base)
        print('PASS: NGINX config/health, SPA/assets, login/cookies/CSRF/Host, 8 MiB upload, 413, media, demo, download, logout and IP-spoof protection.')
        if args.postgres:
            docker('exec', worker, 'python', 'scripts/worker.py', '--healthcheck')
            print('PASS: shared-mode connection, packaged SQL schema and real PostgreSQL identity.')
    except Exception:
        # All fixture data is synthetic. No live application logs are accessed.
        print(docker('logs', backend, check=False))
        print(docker('logs', proxy, check=False))
        if args.postgres:
            print(docker('logs', worker, check=False))
        raise
    finally:
        docker('rm', '-f', proxy, backend, check=False)
        if args.postgres:
            docker('rm', '-f', worker, check=False)
            docker('rm', '-f', '-v', database, check=False)
            docker('volume', 'rm', volume, check=False)
        docker('network', 'rm', name, check=False)


if __name__ == '__main__':
    main()
