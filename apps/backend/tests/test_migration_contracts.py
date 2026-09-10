import hashlib
import json
import threading
import pytest
from urllib.error import HTTPError
from urllib.request import urlopen

from realcenter_marketing.bootstrap.paths import AppPaths
from realcenter_marketing.infrastructure.persistence.filesystem import media_catalog, snapshot
from realcenter_marketing.infrastructure.resources import agent_directory, load_manifest, prompt_version
from realcenter_marketing.presentation.http.server import make_server


def test_legacy_media_id_and_interrupted_run_remain_readable(tmp_path):
    run_id = 'run-' + 'c' * 32
    directory = tmp_path / 'campaigns/runs' / run_id
    directory.mkdir(parents=True)
    image = directory / 'feed-original.png'
    image.write_bytes(b'legacy-file')
    (directory / 'events.jsonl').write_text(json.dumps({'event': 'run_started', 'mode': 'live'}) + '\n', encoding='utf-8')
    expected = hashlib.sha256(f'campaigns/runs/{run_id}/feed-original.png'.encode()).hexdigest()[:24]
    assert media_catalog(tmp_path)[expected]['url'] == '/media/' + expected
    run = snapshot(tmp_path)[0]
    assert run['status'] == 'interrupted'
    assert run['images'][0]['id'] == expected
    assert image.read_bytes() == b'legacy-file'


def test_agent_folder_aliases_preserve_manifest_ids(tmp_path):
    assert agent_directory(tmp_path, 'creative').name == 'creative_producer'
    assert load_manifest(tmp_path, 'creative').id == 'A20'
    assert agent_directory(tmp_path, 'performance').name == 'performance_marketing'
    assert load_manifest(tmp_path, 'performance').status == 'planned'
    manifest = load_manifest(tmp_path, 'creative')
    assert prompt_version(manifest, 'one', 'policy') != prompt_version(manifest, 'two', 'policy')


def test_explicit_data_path_and_static_path_are_independent(tmp_path, monkeypatch):
    monkeypatch.setenv('REALCENTER_DATA_ROOT', str(tmp_path / 'data'))
    monkeypatch.setenv('REALCENTER_STATIC_ROOT', str(tmp_path / 'web'))
    paths = AppPaths.discover()
    assert paths.data_root == tmp_path / 'data'
    assert paths.static_root == tmp_path / 'web'


def test_http_serves_configured_static_build_and_preserves_read_contracts(tmp_path, monkeypatch):
    static = tmp_path / 'web'
    static.mkdir()
    (static / 'index.html').write_text('<html>studio</html>', encoding='utf-8')
    monkeypatch.setenv('REALCENTER_STATIC_ROOT', str(static))
    server = make_server(tmp_path / 'data', port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        assert urlopen(base + '/').read() == b'<html>studio</html>'
        config = json.load(urlopen(base + '/api/config'))
        assert set(config) == {'token', 'configured', 'model', 'image_model'}
        assert json.load(urlopen(base + '/api/runs')) == {'runs': [], 'active_id': None}
        assert json.load(urlopen(base + '/api/media')) == []
        assert len(json.load(urlopen(base + '/api/formats'))) == 6
        assert json.load(urlopen(base + '/api/system/activity')) == []
        missing = 'run-' + 'f' * 32
        with pytest.raises(HTTPError) as error:
            urlopen(base + f'/api/runs/{missing}/files/diagnostics.json')
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
