"""Versioned agent resources and legacy-compatible test/local overrides."""
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Literal

from pydantic import Field
from studio_ai.domain.campaigns import StructuredModel, Text
from studio_ai.domain.tenant import TenantProfile

ROLE_FOLDERS = {'creative': 'creative_producer', 'performance': 'performance_marketing'}


class AgentManifest(StructuredModel):
    id: Text
    name: Text
    status: Literal['active', 'planned']
    responsibilities: list[Text] = Field(min_length=1)
    allowed_tools: list[Text]
    restrictions: list[Text] = Field(min_length=1)


def resources_root():
    configured = os.environ.get('REALCENTER_RESOURCES_ROOT')
    if configured:
        return Path(configured).resolve()
    workspace = next((p for p in Path(__file__).resolve().parents if (p / 'resources/agents').is_dir()), None)
    if workspace is None:
        raise ValueError('Configure REALCENTER_RESOURCES_ROOT com os recursos dos agentes')
    return workspace / 'resources'


def root_overrides_allowed():
    """A data root may replace agent instructions and the policy only when explicitly
    allowed. The default is off: in a shared deployment the data root belongs to the
    tenant, and an override there would silence agent-policy.md — the file that forbids
    inventing prices, expiry dates and addresses."""
    return os.environ.get('REALCENTER_ALLOW_ROOT_OVERRIDES', '') == '1'


def agent_directory(root, role):
    if role not in {'marketing_director', 'social_media', 'copywriter', 'creative', 'performance', 'marketing_analyst'}:
        raise ValueError('Agente desconhecido')
    legacy = root / 'agents' / role
    if root_overrides_allowed() and legacy.is_dir():
        return legacy
    return resources_root() / 'agents' / ROLE_FOLDERS.get(role, role)


def load_manifest(root, role):
    return AgentManifest.model_validate_json((agent_directory(root, role) / 'manifest.json').read_text(encoding='utf-8'))


def load_instructions(root, role):
    text = (agent_directory(root, role) / 'instructions.md').read_text(encoding='utf-8')
    return render(text, load_profile(root))


PLACEHOLDER = re.compile(r'\{\{\s*([a-z_]+)\s*\}\}')


def load_profile(root):
    """The store's own identity. A missing file yields an empty profile, never a fallback
    to whichever store happened to be first."""
    path = root / 'tenant.json'
    if not path.is_file():
        return TenantProfile()
    try:
        return TenantProfile.model_validate_json(path.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return TenantProfile()


def render(text, profile):
    """Substitute {{field}} placeholders, dropping any line whose value is empty.

    Dropping the whole line matters: leaving "Inclua o endereço:" with nothing after it
    is an invitation for the model to invent one, which agent-policy.md forbids. The
    substitution is a regex rather than str.format_map because Brand Kit markdown may
    legitimately contain braces, and format_map would crash on them.
    """
    values = profile.placeholders()
    kept = []
    for line in text.splitlines():
        names = PLACEHOLDER.findall(line)
        if names and any(not values.get(name, '') for name in names):
            continue
        kept.append(PLACEHOLDER.sub(lambda match: values.get(match.group(1), ''), line))
    return chr(10).join(kept)


def load_claims(pack):
    path = resources_root() / 'claims' / f'{pack}.md'
    return path.read_text(encoding='utf-8') if path.is_file() else ''


def category_catalog():
    return json.loads((resources_root() / 'catalog/store-categories.json').read_text(encoding='utf-8'))


def load_policy(root):
    path = root / 'config/agent-policy.md'
    if not (root_overrides_allowed() and path.is_file()):
        path = resources_root() / 'policies/agent-policy.md'
    profile = load_profile(root)
    policy = render(path.read_text(encoding='utf-8'), profile)
    catalog = {item['name']: item['claim_packs'] for item in category_catalog()}
    packs = [profile.pack]
    for category in profile.categories:
        packs.extend(catalog.get(category, ['varejo_geral']))
    claims = '\n\n'.join(load_claims(pack) for pack in dict.fromkeys(packs))
    return policy + chr(10) + chr(10) + claims if claims else policy


# Only the Creative directs the art, so only it is charged for the visual guides.
# The others plan, write and validate: identity and voice are what they act on.
# A role absent from this map receives the whole kit.
BRAND_SCOPE = {
    'performance': ('brand.md', 'tone-of-voice.md'),
    'marketing_analyst': ('brand.md', 'tone-of-voice.md'),
    'marketing_director': ('brand.md', 'tone-of-voice.md'),
    'social_media': ('brand.md', 'tone-of-voice.md'),
    'copywriter': ('brand.md', 'tone-of-voice.md'),
}


def load_brand(root, role=None):
    """Generation guidance for one role.

    The Brand Kit is repeated in every agent's instructions, so a file that does not
    steer that agent is paid for on every request it makes. READMEs document folder
    mechanics and the quality checklist is a human review list run after the art
    exists; neither belongs in any prompt.
    """
    files = sorted(path for path in (root / 'brand').rglob('*.md')
                   if path.name.lower() not in {'readme.md', 'quality-checklist.md'})
    if not files:
        raise ValueError('Brand Kit ausente: crie os arquivos em brand/')
    scope = BRAND_SCOPE.get(role)
    if scope:
        # Never send an empty kit: an unexpected layout falls back to everything.
        files = [path for path in files if path.name in scope] or files
    return json.dumps({str(p.relative_to(root)): p.read_text(encoding='utf-8') for p in files}, ensure_ascii=False)


def prompt_version(manifest, instructions, policy):
    return hashlib.sha256((manifest.model_dump_json() + '\n' + instructions + '\n' + policy).encode()).hexdigest()
