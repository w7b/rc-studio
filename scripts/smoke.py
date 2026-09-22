"""Offline packaged-app smoke test. Only temporary synthetic data is used."""
import json
import re
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

from realcenter_marketing.presentation.http.server import make_server
from realcenter_marketing.infrastructure.identity.database import SCHEMA


def main():
    # Editable installs find this next to the source; wheels must package it too.
    assert SCHEMA.is_file(), 'O pacote instalado não inclui o schema de identidade'
    with tempfile.TemporaryDirectory(prefix='realcenter-smoke-') as directory:
        root = Path(directory)
        (root / 'brand').mkdir()
        (root / 'brand/brand.md').write_text('Marca sintética para teste offline. Fatos comerciais pendentes.', encoding='utf-8')
        server = make_server(root, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            def get(path):
                return json.load(urlopen(base + path, timeout=10))

            html = urlopen(base + '/', timeout=10).read().decode()
            assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
            assert assets and all(urlopen(base + asset, timeout=10).status == 200 for asset in assets)
            config = get('/api/config')
            assert not config['configured']
            payload = json.dumps({'request': 'Campanha de demonstração', 'mode': 'demo'}).encode()
            request = Request(base + '/api/runs', data=payload,
                              headers={'Content-Type': 'application/json', 'X-App-Token': config['token']})
            run_id = json.load(urlopen(request, timeout=10))['id']
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                runs = get('/api/runs')
                if not runs['active_id']:
                    break
                time.sleep(.05)
            assert runs['runs'][0]['status'] == 'completed', runs
            assert runs['runs'][0]['outputs']['campaign']['delegation_log'] == ['social_media', 'copywriter', 'creative']
            assert get(f'/api/runs/{run_id}/draft')['mode'] == 'demo'
            assert urlopen(base + f'/api/runs/{run_id}/files/legenda-feed.txt', timeout=10).status == 200
            assert len(get('/api/formats')) == 6
            assert get('/api/references') == []
            logs = get('/api/logs')
            assert logs['scope'] == 'local' and logs['entries'], logs
            print('PASS: static assets, HTTP contracts, demo agents, saved outputs, downloads and logs; no provider calls.')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)


if __name__ == '__main__':
    main()
