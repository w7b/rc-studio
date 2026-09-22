"""Isolated browser-test server. Only fake local identities; never loads production data.

Run from the repository root with the backend development dependencies available.
"""
import os
import sys
import tempfile
from pathlib import Path

repo = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo / 'apps/backend/tests'))
sys.path.insert(0, str(repo / 'apps/backend/src'))

from identity_fake import FakeIdentityStore
from test_auth_http import FastHasher, NoDatabase
from realcenter_marketing.application.identity.service import IdentityService
from realcenter_marketing.bootstrap.platform import Identity
from realcenter_marketing.infrastructure.identity.rate_limit import MemoryRateLimiter
from realcenter_marketing.presentation.http.server import make_server


if __name__ == '__main__':
    workspace = repo / '.architecture-work'
    workspace.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ui-fixture-', dir=workspace) as temporary:
        root = Path(temporary)
        os.environ['REALCENTER_ENV_ROOT'] = str(root)
        os.environ['REALCENTER_STATIC_ROOT'] = str(repo / 'apps/frontend/dist')
        os.environ['REALCENTER_PUBLIC_SCHEME'] = 'http'
        os.environ['REALCENTER_COOKIE_SECURE'] = '0'
        store = FakeIdentityStore()
        tenant = store.create_tenant('loja-teste', 'Loja de teste', str(root / 'loja'))
        for email, role in [('owner@example.test', 'OWNER'), ('member@example.test', 'PAID')]:
            user = store.create_user(email, 'fake$senha-de-teste-123', 'Pessoa de teste')
            store.grant(user.id, tenant.id, role)
        for i in range(10):
            store.create_tenant(f'loja-{i}', f'Loja {i:02}', str(root / f'loja-{i}'))
        identity = Identity(IdentityService(store, FastHasher(), MemoryRateLimiter()), NoDatabase(), {})
        server = make_server(root, 8767, identity=identity)
        print('Isolated UI fixture: http://127.0.0.1:8767', flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
