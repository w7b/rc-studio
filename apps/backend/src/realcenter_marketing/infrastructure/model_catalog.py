"""Models the studio can run, and the endpoint each one needs.

One vocabulary shared by the dropdown, the agent runtime and the image backend.
Ids carry their provider ('openai:', 'nvidia:') because the same slug can exist
on more than one endpoint, and 'demo' stays a first-class option so the UI can
offer offline fixtures next to the real models.

Each image option also declares what its renderer can take, so the prompt
builder never describes inputs the provider will not receive and never applies
one provider's request limits to another.
"""
from dataclasses import dataclass

NVIDIA_TEXT_URL = 'https://integrate.api.nvidia.com/v1'
NVIDIA_IMAGE_URL = 'https://ai.api.nvidia.com/v1/genai'

DEMO = 'demo'

# https://developers.openai.com/api/reference/resources/images/methods/edit
OPENAI_IMAGE_PROMPT_CHARS = 32_000
OPENAI_IMAGE_REFERENCES = 16

# FLUX.1-dev rejects any other side, and refuses fewer than 5 steps.
FLUX_SIDES = (768, 832, 896, 960, 1024, 1088, 1152, 1216, 1280, 1344)
FLUX_STEPS = 30
# Its text encoder truncates a long prompt instead of refusing it, so a full Brand Kit
# dump would silently push out the headline. A short curated brief keeps the comparison
# about the model rather than about which guide happened to fit.
FLUX_PROMPT_CHARS = 1_500


@dataclass(frozen=True)
class ModelOption:
    id: str
    label: str
    provider: str
    model: str
    note: str = ''
    # The Director delegates through tools while returning a validated review, so a
    # model that cannot do both at once can never finish a campaign.
    delegates: bool = True
    # Image capabilities. A text-to-image renderer never sees product, logo or brand
    # references, so the prompt must not claim they were attached.
    accepts_references: bool = True
    max_prompt_chars: int = OPENAI_IMAGE_PROMPT_CHARS
    max_references: int = OPENAI_IMAGE_REFERENCES

    def public(self, available):
        return {'id': self.id, 'label': self.label, 'provider': self.provider,
                'model': self.model, 'note': self.note, 'available': available,
                'delegates': self.delegates, 'accepts_references': self.accepts_references}


# Measured against build.nvidia.com: with tools alone the model answers
# finish_reason='tool_calls'; adding response_format json_schema silently drops every
# tool call and returns the JSON directly. The Director needs both at once.
KIMI_K3 = ModelOption('nvidia:moonshotai/kimi-k3', 'Kimi K3 · NVIDIA', 'nvidia',
                      'moonshotai/kimi-k3',
                      'A NVIDIA desliga o tool calling quando há saída estruturada, '
                      'então este modelo não consegue delegar aos especialistas.',
                      delegates=False)
FLUX_DEV = ModelOption('nvidia:black-forest-labs/flux.1-dev', 'FLUX.1 dev · NVIDIA', 'nvidia',
                       'black-forest-labs/flux.1-dev',
                       'Comparativo de arte. Sem referências de marca e apenas no feed quadrado.',
                       accepts_references=False, max_prompt_chars=FLUX_PROMPT_CHARS,
                       max_references=0)


def default_text(settings):
    """The .env model stays the default even when unset, so an unconfigured
    server still fails with the original OPENAI_API_KEY/OPENAI_MODEL message."""
    return ModelOption('openai:' + settings.model, (settings.model or 'OpenAI') + ' · OpenAI',
                       'openai', settings.model, 'Modelo do .env')


def default_image(settings):
    return ModelOption('openai:' + settings.image_model, settings.image_model + ' · OpenAI',
                       'openai', settings.image_model,
                       'Padrão: usa foto do produto, logo e brand kit')


def text_models(settings):
    """OpenAI first: it is the configured default and the only one with tools."""
    options = [default_text(settings)] if settings.model else []
    options.append(KIMI_K3)
    return options


def image_models(settings):
    options = [default_image(settings)] if settings.image_model else []
    options.append(FLUX_DEV)
    return options


def find(options, model_id):
    return next((option for option in options if option.id == model_id), None)


def resolve_text(settings, model_id):
    """None means 'whatever the .env configures', preserving previous behaviour."""
    return default_text(settings) if not model_id else find(text_models(settings), model_id)


def resolve_image(settings, model_id):
    return default_image(settings) if not model_id else find(image_models(settings), model_id)


def flux_canvas(width, height):
    """Largest allowed FLUX box that matches the export ratio without upscaling.

    Returns None when the export is larger than FLUX can draw; the caller refuses
    the run instead of enlarging pixels the model never produced.
    """
    target = width / height
    candidates = [(w, h) for w in FLUX_SIDES for h in FLUX_SIDES
                  if abs(w / h / target - 1) <= .02 and w >= width and h >= height]
    return min(candidates, key=lambda box: box[0] * box[1]) if candidates else None
