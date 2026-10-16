"""Platform-owned entitlements. Integration configuration cannot grant a module."""
# Two of these used to be entitlements of their own and are now folded into the module
# they belong with: the marketing consultancy plans paid media, so it rides with Meta
# Ads, and references are material the Library holds. One switch for the operator,
# instead of two that only ever made sense together.
MODULES = {
    'campaigns': 'Campanhas', 'art_lib': 'Biblioteca e referências',
    'erp': 'ERP e relatórios', 'meta_ads': 'Meta Ads e consultoria',
    'agents': 'Consumo dos agentes', 'logs': 'Logs',
}

# Kept so a store saved before the merge still resolves instead of losing access.
RETIRED_MODULES = {'marketing': 'meta_ads', 'references': 'art_lib'}


def module_defaults(overrides=None):
    stored = dict(overrides or {})
    # A retired key still decides its successor when the successor was never stored.
    for retired, successor in RETIRED_MODULES.items():
        if retired in stored and successor not in stored:
            stored[successor] = stored[retired]
    return {key: stored.get(key, True) is True for key in MODULES}


def required_modules(path, payload=None):
    """Any one of the returned entitlements permits a shared media read."""
    if path == '/api/consultations':
        return ('meta_ads',)
    if path.startswith('/api/runs') or path == '/api/brief-assist':
        return ('campaigns',)
    if path.startswith('/api/references'):
        return ('art_lib',)
    if path.startswith('/api/media/'):
        return ('art_lib',)
    if path == '/api/media' or path.startswith('/media/'):
        return ('campaigns', 'art_lib')
    if path == '/api/usage' or path.startswith('/api/system/'):
        return ('agents',)
    if path.startswith('/api/logs'):
        return ('logs',)
    if path == '/api/integrations/meta-ads/validate':
        return ('meta_ads',)
    if path == '/api/integrations':
        return (payload.get('module', ''),) if payload is not None else ('erp', 'meta_ads')
    return ()
