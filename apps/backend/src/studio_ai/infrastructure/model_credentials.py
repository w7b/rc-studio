"""Owner-managed provider overrides, stored in the platform's private configuration.

Never read this file from the tenant's data directory. The trusted composition root
supplies the platform directory and the tenant root registered by the server.
"""
import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path

from studio_ai.infrastructure.model_catalog import PROVIDERS as _REGISTRY

# Derived from the one registry, so the key screen gains a provider the moment the
# catalog does, with no edit here and none in the frontend.
PROVIDERS = {name: provider.label for name, provider in _REGISTRY.items()}
ENV_KEYS = {name: provider.env_key for name, provider in _REGISTRY.items()}
_guard = threading.RLock()


def _path(platform_root, tenant_root):
    identity = os.path.normcase(str(Path(tenant_root).resolve()))
    digest = hashlib.sha256(identity.encode('utf-8')).hexdigest()
    return Path(platform_root) / '.model-keys' / f'{digest}.json'


def load(platform_root, tenant_root):
    path = _path(platform_root, tenant_root)
    try:
        values = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        raise ValueError('Não foi possível ler as chaves de modelos desta loja') from None
    if not isinstance(values, dict) or any(
        key not in PROVIDERS or not isinstance(value, str) or not value for key, value in values.items()
    ):
        raise ValueError('Configuração de chaves da loja inválida')
    return values


def public(platform_root, tenant_root, inherited):
    own = load(platform_root, tenant_root)
    return {'providers': {provider: {
        'label': label,
        'configured': bool(own.get(provider) or inherited.get(ENV_KEYS[provider])),
        'source': 'store' if own.get(provider) else 'platform' if inherited.get(ENV_KEYS[provider]) else 'missing',
        'inherited_configured': bool(inherited.get(ENV_KEYS[provider])),
    } for provider, label in PROVIDERS.items()}}


def save(platform_root, tenant_root, changes):
    if not isinstance(changes, dict) or not changes or any(key not in PROVIDERS for key in changes):
        raise ValueError('Informe os provedores que deseja atualizar')
    checked = {}
    for provider, value in changes.items():
        if not isinstance(value, dict) or value.get('action') not in ('replace', 'inherit'):
            raise ValueError('Escolha substituir a chave ou herdar a configuração da plataforma')
        if value['action'] == 'inherit':
            checked[provider] = None
            continue
        key = value.get('key')
        if not isinstance(key, str) or not key.strip() or len(key) > 8192 or any(c.isspace() for c in key.strip()):
            raise ValueError('Informe uma chave válida, sem espaços, para o provedor')
        checked[provider] = key.strip()
    with _guard:
        stored = load(platform_root, tenant_root)
        for provider, key in checked.items():
            if key is None:
                stored.pop(provider, None)
            else:
                stored[provider] = key
        path = _path(platform_root, tenant_root)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix='.keys-', dir=path.parent)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
                json.dump(stored, output)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
