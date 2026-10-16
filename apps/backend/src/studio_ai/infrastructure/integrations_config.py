"""Per-store integration settings.

ERP and Meta Ads were static placeholders describing one company's vendor. Every store has
its own supplier, its own account and its own credentials, so the configuration belongs to
the store's data root rather than to the product.

Secrets are write-only over the API: they are stored, never read back. A support request
should not be able to retrieve a customer's ERP password by opening a settings screen.
"""
import json
import threading

_guard = threading.RLock()

FIELDS = {
    'erp': ('provider', 'base_url', 'company_id', 'username'),
    'meta_ads': ('business_id', 'ad_account_id', 'page_id', 'api_version'),
}
SECRETS = {'erp': ('password', 'api_key'), 'meta_ads': ('access_token',)}


def _path(root):
    return root / 'integrations.json'


def load(root):
    try:
        stored = json.loads(_path(root).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        stored = {}
    return stored if isinstance(stored, dict) else {}


def public(root):
    """What a settings screen may display: values, plus a flag per secret."""
    stored = load(root)
    view = {}
    for module, fields in FIELDS.items():
        section = stored.get(module) or {}
        view[module] = {
            'enabled': bool(section.get('enabled')),
            **{field: section.get(field, '') for field in fields},
            'secrets': {name: bool(section.get(name)) for name in SECRETS[module]},
            'validation': section.get('validation'),
            'publishing_available': False,
        }
    return view


def save(root, module, values):
    with _guard:
        return _save(root, module, values)


def _save(root, module, values):
    if module not in FIELDS:
        raise ValueError('Integração desconhecida')
    if not isinstance(values, dict):
        raise ValueError('Envie os campos da integração')
    stored = load(root)
    section = dict(stored.get(module) or {})
    section.pop('validation', None)
    section['enabled'] = bool(values.get('enabled'))
    for field in FIELDS[module]:
        if field in values:
            section[field] = str(values[field] or '').strip()[:400]
    for name in SECRETS[module]:
        supplied = values.get(name)
        if supplied:
            # An empty field means "leave it alone", so a form that never shows the
            # secret cannot blank it out by being submitted.
            section[name] = str(supplied).strip()[:8192]
        elif values.get(f'clear_{name}'):
            section.pop(name, None)
    stored[module] = section
    _write(root, stored)
    return public(root)


def _write(root, stored):
    _path(root).parent.mkdir(parents=True, exist_ok=True)
    temporary = _path(root).with_suffix('.json.tmp')
    temporary.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(_path(root))


def validate_meta(root):
    from .integrations.meta_ads import validate_connection
    with _guard:
        settings = dict(load(root).get('meta_ads') or {})
    result = validate_connection(settings)
    with _guard:
        stored = load(root)
        # A saved edit invalidates an in-flight diagnostic instead of certifying old credentials.
        if stored.get('meta_ads', {}) != settings:
            raise ValueError('A configuração mudou durante a validação. Valide novamente.')
        stored.setdefault('meta_ads', {})['validation'] = result
        _write(root, stored)
    return result
