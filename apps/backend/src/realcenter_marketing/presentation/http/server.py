import argparse
import signal
import json
import mimetypes
import secrets
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError

from realcenter_marketing.application.commands import AssistRequest, ImageRequest, RunRequest, ReferenceRequest
from realcenter_marketing.application.errors import BusyError
from realcenter_marketing.domain.publications import catalog as publication_catalog


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, service, token, **kwargs):
        self.service, self.token = service, token
        super().__init__(*args, **kwargs)

    def reply(self, status, body, mime='application/json; charset=utf-8', download=None):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'")
        if download:
            self.send_header('Content-Disposition', f'attachment; filename="{download}"')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def local_host(self):
        return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

    def do_GET(self):
        if not self.local_host():
            return self.reply(403, {'error': 'Host inválido'})
        path = urlsplit(self.path).path
        queries = self.server.container.queries
        if path == '/api/system':
            return self.reply(200, self.server.catalog.snapshot())
        if path == '/api/system/activity':
            return self.reply(200, queries.activity())
        if path == '/api/usage':
            return self.reply(200, queries.usage())
        if path == '/api/formats':
            return self.reply(200, publication_catalog())
        if path == '/api/references':
            return self.reply(200, queries.references())
        reference_parts = path.strip('/').split('/')
        if len(reference_parts) == 4 and reference_parts[:2] == ['api', 'references'] and reference_parts[3] in ('image', 'download'):
            try:
                content, name = queries.reference_file(reference_parts[2])
                return self.reply(200, content, mimetypes.guess_type(name)[0], name if reference_parts[3] == 'download' else None)
            except (ValueError, OSError):
                return self.reply(404, {'error': 'Referência não encontrada'})
        if path == '/api/config':
            return self.reply(200, {'token': self.token, **self.server.container.public_config()})
        if path == '/api/runs':
            active_id = self.service.active_id
            return self.reply(200, {'runs': queries.runs(active_id), 'active_id': active_id})
        if path == '/api/media':
            return self.reply(200, queries.media())
        if path.startswith('/media/'):
            try:
                content, name = queries.media_file(path[7:])
                return self.reply(200, content, mimetypes.guess_type(name)[0] or 'application/octet-stream')
            except (ValueError, OSError):
                return self.reply(404, {'error': 'Não encontrado'})
        parts = path.strip('/').split('/')
        if len(parts) == 4 and parts[:2] == ['api', 'runs'] and parts[3] == 'draft':
            try:
                return self.reply(200, self.service.saved_request(parts[2]).model_dump())
            except (ValueError, OSError):
                return self.reply(404, {'error': 'Briefing não encontrado'})
        if len(parts) == 5 and parts[:2] == ['api', 'runs'] and parts[3] == 'files':
            try:
                content, mime = queries.artifact(parts[2], parts[4])
                return self.reply(200, content, mime, download=parts[4])
            except (ValueError, OSError):
                pass
        static = self.server.paths.static_root
        file = static / 'index.html' if path == '/' else (static / path.lstrip('/')).resolve() if path.startswith('/assets/') else None
        if file and file.resolve().is_relative_to(static.resolve()) and file.is_file():
            return self.reply(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
        return self.reply(404, {'error': 'Não encontrado'})

    def do_POST(self):
        expected_origin = 'http://' + self.headers.get('Host', '')
        if not self.local_host() or self.headers.get('Origin', expected_origin) != expected_origin or not secrets.compare_digest(self.headers.get('X-App-Token', ''), self.token):
            return self.reply(403, {'error': 'Recarregue o app para iniciar a execução'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.reply(415, {'error': 'Envie JSON'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 23 * 1024 * 1024:
                return self.reply(413, {'error': 'Upload excedeu o limite'})
            payload = json.loads(self.rfile.read(length))
            path = urlsplit(self.path).path
            if path == '/api/brief-assist':
                return self.reply(200, self.service.assist(AssistRequest.model_validate(payload)))
            if path == '/api/references':
                return self.reply(201, self.server.container.queries.save_reference(ReferenceRequest.model_validate(payload)))
            if path == '/api/runs':
                run_id = self.service.start(RunRequest.model_validate(payload))
                return self.reply(202, {'id': run_id})
            parts = path.strip('/').split('/')
            if len(parts) == 4 and parts[:2] == ['api', 'runs'] and parts[3] == 'retry':
                return self.reply(202, {'id': self.service.retry(parts[2])})
            if len(parts) == 4 and parts[:2] == ['api', 'runs'] and parts[3] == 'delete':
                self.service.delete(parts[2])
                return self.reply(200, {'deleted': parts[2]})
            if len(parts) == 4 and parts[:2] == ['api', 'runs'] and parts[3] == 'image':
                self.service.image(parts[2], ImageRequest.model_validate(payload))
                return self.reply(202, {'id': parts[2]})
            return self.reply(404, {'error': 'Não encontrado'})
        except BusyError as exc:
            return self.reply(409, {'error': str(exc)})
        except ValidationError:
            return self.reply(400, {'error': 'Confira o briefing e os campos enviados'})
        except (ValueError, json.JSONDecodeError) as exc:
            message = str(exc) if type(exc) is ValueError else 'JSON inválido'
            return self.reply(400, {'error': message[:180]})
        except Exception:
            return self.reply(500, {'error': 'Não foi possível iniciar a execução'})

    def log_message(self, *args):
        pass


class StudioServer(ThreadingHTTPServer):
    def server_close(self):
        super().server_close()
        if hasattr(self, 'container'):
            self.container.close()


def make_server(root=None, port=8765, host='127.0.0.1'):
    from realcenter_marketing.bootstrap.container import build_container
    container = build_container(root)
    try:
        server = StudioServer((host, port), partial(Handler, service=container.service, token=secrets.token_urlsafe(32)))
        server.container = container
        server.paths, server.service, server.catalog = container.paths, container.service, container.catalog
        server.catalog.start()
        return server
    except BaseException:
        container.close()
        raise


def main():
    parser = argparse.ArgumentParser(description='Real Center Studio — app local')
    parser.add_argument('--project-root', type=Path, default=None)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--host', choices=['127.0.0.1', '0.0.0.0'], default='127.0.0.1')
    args = parser.parse_args()
    server = make_server(args.project_root, args.port, args.host)
    print(f'Real Center Studio: http://127.0.0.1:{args.port}', flush=True)
    def terminate(signum, frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, terminate)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, previous)
        server.server_close()


if __name__ == '__main__':
    main()
