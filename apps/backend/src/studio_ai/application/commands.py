from typing import Annotated, Literal
from pydantic import Field, StringConstraints, model_validator
from studio_ai.domain.campaigns import StructuredModel
from studio_ai.domain.publications import Publication

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
    # Picked from what the store already uploaded, instead of carrying the bytes again.
    reference_id: str | None = Field(default=None, max_length=200)
    upload: str | None = Field(default=None, max_length=11200000)
    reference_upload: str | None = Field(default=None, max_length=11200000)

class RenameRequest(StructuredModel):
    title: str = Field(min_length=1, max_length=120)


class ImageRequest(StructuredModel):
    image_model_id: str | None = Field(default=None, max_length=200)
    changes: str = Field(default='', max_length=4000)
    base_image_id: str | None = None
    reference_upload: str | None = Field(default=None, max_length=11200000)

class AssistRequest(StructuredModel):
    request: str = Field(min_length=1, max_length=12000)
    model_id: str | None = Field(default=None, max_length=200)
    confirmed_facts: list[ShortText] = Field(default_factory=list, max_length=100)

class BriefSuggestion(StructuredModel):
    improved_request: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=12000)]
    changes: list[ShortText] = Field(max_length=8)
    questions: list[ShortText] = Field(max_length=8)


class ReferenceRequest(StructuredModel):
    url: str = Field(default='', max_length=2048)
    title: str = Field(default='', max_length=120)
    kind: Literal['feed', 'story', 'youtube', 'product'] = 'feed'
    upload: str | None = Field(default=None, max_length=12 * 1024 * 1024)


class ReferenceCrop(StructuredModel):
    x: int = Field(ge=0, le=25000000)
    y: int = Field(ge=0, le=25000000)
    width: int = Field(ge=1, le=25000000)
    height: int = Field(ge=1, le=25000000)


class ReferenceEditRequest(StructuredModel):
    reference_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    operation: Literal['crop', 'enhance', 'remove_background', 'qwen']
    title: str = Field(default='', max_length=120)
    crop: ReferenceCrop | None = None
    scale: Literal[1, 2] = 1
    tolerance: int = Field(default=25, ge=0, le=80)
    prompt: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def validate_operation(self):
        if self.operation == 'crop' and self.crop is None:
            raise ValueError('Informe a área de recorte')
        if self.operation == 'qwen' and not self.prompt.strip():
            raise ValueError('Descreva a edição desejada')
        return self
