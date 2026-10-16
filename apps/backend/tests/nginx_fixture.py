"""Synthetic shared server for scripts/smoke_nginx.py. No real data or providers."""
import os
import tempfile
from pathlib import Path

from identity_fake import FakeIdentityStore
from studio_ai.application.identity.service import IdentityService
from studio_ai.bootstrap.platform import Identity, build_identity
from studio_ai.infrastructure.identity.rate_limit import MemoryRateLimiter
from studio_ai.presentation.http.server import make_server


class FixtureHasher:
    def hash(self, value):
        return 'fixture$' + value

    def verify(self, value, encoded):
        return encoded == self.hash(value)

    def dummy_verify(self):
        pass


class FixtureDatabase:
    def close(self):
        pass


with tempfile.TemporaryDirectory(prefix='studio-nginx-', dir=os.environ.get('SMOKE_DATA_ROOT')) as directory:
    root = Path(directory)
    (root / 'brand').mkdir()
    (root / 'brand/brand.md').write_text('Marca sintética de teste. Não inventar fatos.', encoding='utf-8')
    if os.environ.get('SMOKE_POSTGRES') == '1':
        identity = build_identity()
        store = identity.service.store
    else:
        store = FakeIdentityStore()
        identity = Identity(IdentityService(store, FixtureHasher(), MemoryRateLimiter()), FixtureDatabase(), {})
    tenant = store.create_tenant('proxy-test', 'Loja de teste', str(root))
    password = identity.service.hasher.hash('senha-de-teste-proxy')
    user = store.create_user('proxy@example.test', password, 'Teste')
    store.grant(user.id, tenant.id, 'OWNER')
    server = make_server(root, 8765, host='0.0.0.0', identity=identity)
    try:
        server.serve_forever()
    finally:
        server.server_close()
