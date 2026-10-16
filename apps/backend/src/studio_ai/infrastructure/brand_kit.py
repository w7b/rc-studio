"""Seeding and editing a store's Brand Kit.

A store used to be created with a tenant.json and nothing else, so the first campaign
failed at load_brand with "Brand Kit ausente" — after the owner had already filled in the
whole form. The kit is now written when the store is created, from a neutral base filled
with that store's own identity.

The base is deliberately not Real Center's kit. Copying it would hand every new shop that
store's colours, its supermarket art direction and its language, which is the exact
problem the per-segment work removed. What is reused is the structure: five files, each
with one job, which is the part that proved itself.
"""
from studio_ai.domain.tenant import TenantProfile
from .resources import render, resources_root

# The names are fixed: load_brand globs brand/**/*.md, and image generation reads this
# exact set. A file outside it is still loaded by the agents, but never by the renderer.
FILES = ('brand.md', 'tone-of-voice.md', 'colors.md', 'typography.md', 'visual-guidelines.md')

TITLES = {
    'brand.md': 'Identidade',
    'tone-of-voice.md': 'Tom de voz',
    'colors.md': 'Cores',
    'typography.md': 'Tipografia',
    'visual-guidelines.md': 'Diretrizes visuais',
}

# What each file is for, shown next to the editor so nobody has to guess.
HINTS = {
    'brand.md': 'Quem é a loja, endereço e o que nunca pode aparecer nas peças.',
    'tone-of-voice.md': 'Como a loja fala. Vale para legenda, Stories e WhatsApp.',
    'colors.md': 'Paleta e onde cada cor entra.',
    'typography.md': 'Famílias e hierarquia de texto nas artes.',
    'visual-guidelines.md': 'Direção de arte: composição, foco e o que evitar.',
}

DEFAULTS = {'font_primary': 'uma sans-serif pesada e legível',
            'font_secondary': 'uma sans-serif limpa para textos de apoio',
            'brand_color': '#EF863D'}


def base_text(name, profile):
    """The neutral template with this store's identity written in.

    Values are substituted now rather than at read time so the owner edits real text
    instead of placeholders, and so renaming the store later never silently rewrites
    wording they had adjusted by hand.
    """
    source = resources_root() / 'brandkit' / name
    if not source.is_file():
        return ''
    filled = profile.model_copy(update={field: (getattr(profile, field, '') or fallback)
                                        for field, fallback in DEFAULTS.items()})
    return render(source.read_text(encoding='utf-8'), filled)


def seed(root, profile=None, overwrite=False):
    """Write any missing file. Returns the names actually created."""
    profile = profile or TenantProfile()
    directory = root / 'brand'
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name in FILES:
        target = directory / name
        if target.exists() and not overwrite:
            continue
        text = base_text(name, profile)
        if not text.strip():
            continue
        target.write_text(text, encoding='utf-8')
        written.append(name)
    return written


def read(root):
    directory = root / 'brand'
    files = []
    for name in FILES:
        path = directory / name
        files.append({'name': name, 'title': TITLES[name], 'hint': HINTS[name],
                      'exists': path.is_file(),
                      'content': path.read_text(encoding='utf-8') if path.is_file() else ''})
    # Extra .md files still reach the agents, so the editor has to admit they exist.
    extras = sorted(path.name for path in directory.glob('*.md')
                    if path.name not in FILES
                    and path.name.lower() not in {'readme.md', 'quality-checklist.md'})
    return {'files': files, 'extras': extras,
            'complete': all(entry['exists'] for entry in files)}


def write(root, name, content):
    if name not in FILES:
        raise ValueError('Arquivo do Brand Kit desconhecido')
    if not str(content or '').strip():
        # An empty kit is what produced "Brand Kit ausente" in the first place.
        raise ValueError('O conteúdo não pode ficar vazio')
    directory = root / 'brand'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    temporary = target.with_suffix('.md.tmp')
    temporary.write_text(str(content), encoding='utf-8')
    temporary.replace(target)
    return read(root)
