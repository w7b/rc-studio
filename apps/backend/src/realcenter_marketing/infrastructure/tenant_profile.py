"""Reading and writing a store's own profile.

The address, the phone and the hashtags in a campaign come from here, which is why they
belong to the store rather than to whoever happens to be signed in: two people sharing a
shop must not produce two different addresses on the art.
"""
import json

from realcenter_marketing.domain.tenant import CLAIM_PACKS, DELIVERABLES, TenantProfile

PATH = 'tenant.json'

TEXT_FIELDS = ('brand_name', 'segment', 'city', 'address', 'cta_hint', 'instagram',
               'whatsapp', 'phone', 'brand_color', 'logo', 'font_primary', 'font_secondary')

# Offered in the picker. A store may still type its own, because a licensed brand font
# is not going to be on any list we ship.
FONT_SUGGESTIONS = (
    'Inter', 'Roboto', 'Open Sans', 'Lato', 'Montserrat', 'Poppins', 'Nunito',
    'Source Sans 3', 'Raleway', 'Oswald', 'Bebas Neue', 'Playfair Display',
    'Merriweather', 'Archivo', 'Barlow', 'Work Sans', 'Rubik', 'Manrope',
)


def load(root):
    return TenantProfile() if not (root / PATH).is_file() else _read(root)


def _read(root):
    try:
        return TenantProfile.model_validate_json((root / PATH).read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return TenantProfile()


def options():
    from .resources import category_catalog
    return {'claim_packs': list(CLAIM_PACKS), 'deliverables': list(DELIVERABLES),
            'fonts': list(FONT_SUGGESTIONS), 'categories': category_catalog()}


def save(root, values):
    if not isinstance(values, dict):
        raise ValueError('Envie os campos da loja')
    current = load(root).model_dump()
    for field in TEXT_FIELDS:
        if field in values:
            current[field] = str(values[field] or '').strip()[:300]
    if 'hashtags' in values:
        raw = values['hashtags']
        tags = raw.split() if isinstance(raw, str) else list(raw or [])
        # Stored with the hash so the prompt can use them verbatim.
        current['hashtags'] = [('#' + tag.lstrip('#')) for tag in tags if str(tag).strip()][:12]
    if 'deliverables' in values:
        wanted = [item for item in (values['deliverables'] or []) if item in DELIVERABLES]
        current['deliverables'] = wanted or ['stories', 'feed']
    if 'claim_pack' in values:
        current['claim_pack'] = values['claim_pack'] if values['claim_pack'] in CLAIM_PACKS else current['claim_pack']
    if 'categories' in values:
        from .resources import category_catalog
        catalog = {item['name']: item['claim_packs'] for item in category_catalog()}
        selected = values['categories']
        if (not isinstance(selected, list) or len(selected) > 3
                or any(not isinstance(name, str) or name not in catalog for name in selected)
                or len(set(selected)) != len(selected)):
            raise ValueError('Selecione até 3 categorias diferentes do catálogo')
        had_categories = bool(current.get('categories'))
        current['categories'] = selected
        if selected:
            current['claim_pack'] = catalog[selected[0]][0]
        elif had_categories:
            current['claim_pack'] = 'varejo_geral'

    profile = TenantProfile.model_validate(current)
    root.mkdir(parents=True, exist_ok=True)
    temporary = (root / PATH).with_suffix('.json.tmp')
    temporary.write_text(profile.model_dump_json(indent=2), encoding='utf-8')
    temporary.replace(root / PATH)
    return profile
