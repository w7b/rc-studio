"""Versioned agent resources and legacy-compatible test/local overrides."""
import hashlib
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from realcenter_marketing.domain.campaigns import StructuredModel, Text

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


def agent_directory(root, role):
    if role not in {'marketing_director', 'social_media', 'copywriter', 'creative', 'performance', 'marketing_analyst'}:
        raise ValueError('Agente desconhecido')
    legacy = root / 'agents' / role
    return legacy if legacy.is_dir() else resources_root() / 'agents' / ROLE_FOLDERS.get(role, role)


def load_manifest(root, role):
    return AgentManifest.model_validate_json((agent_directory(root, role) / 'manifest.json').read_text(encoding='utf-8'))


def load_instructions(root, role):
    return (agent_directory(root, role) / 'instructions.md').read_text(encoding='utf-8')


def load_policy(root):
    path = root / 'config/agent-policy.md'
    if not path.is_file():
        path = resources_root() / 'policies/agent-policy.md'
    return path.read_text(encoding='utf-8')


# Only the Creative directs the art, so only it is charged for the visual guides.
# The others plan, write and validate: identity and voice are what they act on.
# A role absent from this map receives the whole kit.
BRAND_SCOPE = {
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
