from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from realcenter_marketing.domain.publications import Publication

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
    leaflet_copy: Text
    whatsapp_draft: Text
    carousel_cards: list[CarouselCard] = Field(default_factory=list, max_length=10)


class AssetBrief(StructuredModel):
    format: Literal["stories", "feed", "leaflet", "banner"]
    dimensions: Text
    layout: Text
    hierarchy: list[Text] = Field(min_length=1)


class CreativeBrief(StructuredModel):
    visual_direction: Text
    leaflet_brief: Text
    assets: list[AssetBrief] = Field(min_length=3)
    brand_pending: list[Text]

    @model_validator(mode="after")
    def required_formats(self):
        if not {"stories", "feed", "leaflet"} <= {a.format for a in self.assets}:
            raise ValueError("Briefing precisa de Stories, Feed e encarte")
        return self


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
