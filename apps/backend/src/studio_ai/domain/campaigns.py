from typing import Annotated, Literal

from .tenant import DEFAULT_DELIVERABLES

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from studio_ai.domain.publications import Publication

SPECIALIST_ROLES = ('social_media', 'copywriter', 'creative')

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class StructuredModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CampaignBrief(StructuredModel):
    request: Text
    confirmed_facts: list[Text] = Field(default_factory=list)
    publication: Publication = Field(default_factory=Publication)
    # The Brand Kit compares a piece against its own family and forbids carrying a
    # drink explosion into a notice, so style references are filtered by this.
    family: Literal['produto', 'institucional'] = 'produto'


class StoryPlan(StructuredModel):
    number: int = Field(ge=1)
    objective: Text
    visual: Text


class CalendarEntry(StructuredModel):
    timing: Text
    format: Literal["stories", "feed", "reel"]
    objective: Text


class SocialPlan(StructuredModel):
    strategy: Text
    audience_hypothesis: Text
    stories: list[StoryPlan] = Field(min_length=3, max_length=7)
    feed_suggestion: Text
    reel_suggestion: Text
    calendar: list[CalendarEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def sequential_stories(self):
        if [s.number for s in self.stories] != list(range(1, len(self.stories) + 1)):
            raise ValueError("Stories devem ter números consecutivos a partir de 1")
        return self


class StoryCopy(StructuredModel):
    number: int = Field(ge=1)
    text: Text
    cta: Text


class CarouselCard(StructuredModel):
    number: int = Field(ge=1, le=10)
    headline: Text
    body: str
    visual: Text
    cta: str


class CopyPack(StructuredModel):
    headline: Text
    cta: Text
    stories: list[StoryCopy] = Field(min_length=3, max_length=7)
    feed_caption: Text
    leaflet_copy: Text | None = None
    whatsapp_draft: Text
    carousel_cards: list[CarouselCard] = Field(default_factory=list, max_length=10)


class AssetBrief(StructuredModel):
    format: Literal["stories", "feed", "leaflet", "banner"]
    dimensions: Text
    layout: Text
    hierarchy: list[Text] = Field(min_length=1)


class CreativeBrief(StructuredModel):
    visual_direction: Text
    leaflet_brief: Text | None = None
    # The floor is one asset; which formats are actually required comes from the
    # store's declared deliverables, checked below.
    assets: list[AssetBrief] = Field(min_length=1)
    brand_pending: list[Text]

    @model_validator(mode="after")
    def required_formats(self, info):
        """The required set comes from the store, not from the product.

        A leaflet is a supermarket artefact. A pet shop, a barber or a clothing store has
        none, and demanding one produced a deliverable nobody asked for. The validation
        context carries the store's declared deliverables; with no context the floor is
        Stories and Feed, which every store publishes."""
        expected = (info.context or {}).get('deliverables')
        required = set(expected or DEFAULT_DELIVERABLES)
        produced = {a.format for a in self.assets}
        if not required <= produced:
            missing = ', '.join(sorted(required - produced))
            raise ValueError(
                f"Briefing precisa dos formatos declarados pela loja: {missing}. "
                "Formatos fora desta campanha entram como briefing condicional, dizendo que "
                "não são produzidos agora — não podem simplesmente sair da lista.")
        return self


class SpecialistBrief(StructuredModel):
    """What the Director hands one specialist before it works.

    This is the same information the delegation tool used to ask for in prose —
    objective, concept and specific guidance — now a validated field instead of a
    free-form argument the model had to remember to fill.
    """
    role: Literal["social_media", "copywriter", "creative"]
    objective: Text
    concept: Text
    guidance: Text


class CampaignPlan(StructuredModel):
    concept: Text
    # The bounds are on the schema, not only in the prompt: a provider that honours
    # strict json_schema then refuses a short plan before it costs a round trip.
    briefs: list[SpecialistBrief] = Field(min_length=len(SPECIALIST_ROLES),
                                          max_length=len(SPECIALIST_ROLES))

    @model_validator(mode="after")
    def validate_coverage(self):
        """One brief per specialist. Order in this list is deliberately not required.

        The pipeline walks SPECIALIST_STEPS and looks each brief up by role, so the order
        the Director happens to write them in is never read. Demanding it anyway failed
        otherwise-valid plans for a property nothing depends on.
        """
        papeis = [brief.role for brief in self.briefs]
        if sorted(papeis) != sorted(SPECIALIST_ROLES):
            faltando = sorted(set(SPECIALIST_ROLES) - set(papeis))
            repetidos = sorted({papel for papel in papeis if papeis.count(papel) > 1})
            detalhe = (f'faltam: {", ".join(faltando)}' if faltando
                       else f'repetidos: {", ".join(repetidos)}')
            raise ValueError(f'Plano precisa de exatamente um briefing por especialista ({detalhe})')
        return self

    def for_role(self, role):
        return next(brief for brief in self.briefs if brief.role == role)


class DirectorReview(StructuredModel):
    strategy: Text
    concept: Text
    assumptions: list[Text]
    pending_information: list[Text]
    review_notes: Text


class Campaign(StructuredModel):
    status: Literal["DRAFT"] = "DRAFT"
    execution_mode: Literal["live", "demo"]
    brief: CampaignBrief
    director: DirectorReview
    social: SocialPlan
    copywriting: CopyPack
    creative: CreativeBrief
    delegation_log: list[Literal["social_media", "copywriter", "creative"]]

    @model_validator(mode="after")
    def validate_composition(self):
        if self.brief.publication.kind == 'carousel':
            if [c.number for c in self.copywriting.carousel_cards] != list(range(1, self.brief.publication.slides + 1)):
                raise ValueError('Copies devem conter todos os cards do carrossel na ordem selecionada')
        if [s.number for s in self.social.stories] != [s.number for s in self.copywriting.stories]:
            raise ValueError("Copies devem corresponder à sequência de Stories planejada")
        if self.delegation_log != list(SPECIALIST_ROLES):
            raise ValueError("Campanha requer as três delegações concluídas em ordem")
        return self
