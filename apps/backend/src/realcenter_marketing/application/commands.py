from typing import Annotated, Literal
from pydantic import Field, StringConstraints
from realcenter_marketing.domain.campaigns import StructuredModel
from realcenter_marketing.domain.publications import Publication

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]

class RunRequest(StructuredModel):
    request: str = Field(min_length=1, max_length=12000)
    confirmed_facts: list[str] = Field(default_factory=list, max_length=100)
    mode: Literal['live', 'demo'] = 'live'
    # Empty means the server default; the UI sends an id from /api/config.
    model_id: str | None = Field(default=None, max_length=200)
    image_model_id: str | None = Field(default=None, max_length=200)
    generate_image: bool = False
    publication: Publication = Field(default_factory=Publication)
    family: Literal['produto', 'institucional'] = 'produto'
    product_id: str | None = None
    upload: str | None = Field(default=None, max_length=11200000)
    reference_upload: str | None = Field(default=None, max_length=11200000)

class ImageRequest(StructuredModel):
    image_model_id: str | None = Field(default=None, max_length=200)
    changes: str = Field(default='', max_length=4000)
    base_image_id: str | None = None
    reference_upload: str | None = Field(default=None, max_length=11200000)

class AssistRequest(StructuredModel):
    request: str = Field(min_length=1, max_length=12000)
    confirmed_facts: list[ShortText] = Field(default_factory=list, max_length=100)

class BriefSuggestion(StructuredModel):
    improved_request: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=12000)]
    changes: list[ShortText] = Field(max_length=8)
    questions: list[ShortText] = Field(max_length=8)


class ReferenceRequest(StructuredModel):
    url: str = Field(default='', max_length=2048)
    title: str = Field(default='', max_length=120)
    kind: Literal['feed', 'story', 'youtube'] = 'feed'
    upload: str | None = Field(default=None, max_length=12 * 1024 * 1024)
