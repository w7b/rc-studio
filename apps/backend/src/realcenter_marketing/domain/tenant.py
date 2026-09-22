"""What a store is, from the agents' point of view.

Everything here used to be hardcoded to one supermarket in Paranavaí: the brand name, the
street address, the hashtags, the obligation to produce a leaflet, and a set of claim
guardrails written for food. None of that generalises. A pet shop has no leaflet, a gym
sells plans rather than priced units, and a pharmacy needs stricter rules than a grocer,
not the same ones.

The safe default everywhere is omission. A missing field removes the instruction rather
than leaving a blank in it, because agent-policy.md forbids inventing an address and a
prompt that says "include the address:" with nothing after it invites exactly that.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# What an agent may be asked to produce. 'leaflet' is the supermarket flyer, and it is no
# longer implied: a store declares what it actually publishes.
DELIVERABLES = ('stories', 'feed', 'leaflet', 'banner')
DEFAULT_DELIVERABLES = ('stories', 'feed')

# Claim guardrails by trade. Concatenated to the shared policy, never replacing it.
CLAIM_PACKS = ('alimento', 'saude', 'servico', 'varejo_geral')
DEFAULT_CLAIM_PACK = 'varejo_geral'


class TenantProfile(BaseModel):
    """Read from tenant.json at the store's data root. Absent means every field empty,
    which is safe: the prompts simply stop asserting things nobody confirmed."""
    model_config = ConfigDict(extra='ignore')

    brand_name: str = ''
    segment: str = ''
    categories: list[str] = Field(default_factory=list, max_length=3)
    city: str = ''
    address: str = ''
    cta_hint: str = ''
    hashtags: list[str] = Field(default_factory=list)
    instagram: str = ''
    whatsapp: str = ''
    phone: str = ''
    # Typography the art direction should follow. Empty means the Brand Kit's own
    # typography.md decides, which is how it worked before these were configurable.
    font_primary: str = ''
    font_secondary: str = ''
    deliverables: list[Literal[DELIVERABLES]] = Field(default_factory=lambda: list(DEFAULT_DELIVERABLES))
    claim_pack: str = DEFAULT_CLAIM_PACK
    brand_color: str = ''
    logo: str = 'brand/logo/logo.png'

    @property
    def complete(self):
        """A store with no name cannot have a campaign written for it — the copy would
        have to invent one."""
        return bool(self.brand_name.strip())

    @property
    def missing(self):
        return [name for name in ('brand_name', 'segment', 'address', 'hashtags')
                if not getattr(self, name)]

    @property
    def fonts(self):
        """Typography instruction for the image prompt, or nothing when unset."""
        primary, secondary = self.font_primary.strip(), self.font_secondary.strip()
        if primary and secondary:
            return f'Use {primary} nos títulos e {secondary} nos textos de apoio.'
        if primary:
            return f'Use {primary} como tipografia principal.'
        return ''

    @property
    def described(self):
        """How the store should be referred to in an image prompt."""
        parts = [', '.join(self.categories) or self.segment.strip(), self.brand_name.strip()]
        return ' '.join(part for part in parts if part) or 'a marca do Brand Kit'

    @property
    def pack(self):
        return self.claim_pack if self.claim_pack in CLAIM_PACKS else DEFAULT_CLAIM_PACK

    def produces(self, deliverable):
        return deliverable in (self.deliverables or DEFAULT_DELIVERABLES)

    def placeholders(self):
        """Values substituted into agent instructions. An empty value deletes the whole
        line that mentions it, so an unfilled field never reaches the model as a gap to
        fill in."""
        return {
            'brand_name': self.brand_name.strip(),
            'segment': ', '.join(self.categories) or self.segment.strip(),
            'city': self.city.strip(),
            'address': self.address.strip(),
            'cta_hint': self.cta_hint.strip(),
            'hashtags': ' '.join(self.hashtags).strip(),
            'instagram': self.instagram.strip(),
            'phone': self.phone.strip(),
            'whatsapp': self.whatsapp.strip(),
            'font_primary': self.font_primary.strip(),
            'font_secondary': self.font_secondary.strip(),
            'logo': self.logo.strip(),
            'deliverables': ', '.join(self.deliverables or DEFAULT_DELIVERABLES),
        }
