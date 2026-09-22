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
# One token reaches hundreds of open models. The endpoint is a drop-in replacement for
# the OpenAI client, and it speaks Chat Completions only, like NVIDIA NIM.
HUGGINGFACE_TEXT_URL = 'https://router.huggingface.co/v1'

DEMO = 'demo'


@dataclass(frozen=True)
class Provider:
    """Everything that used to be an `if provider == ...` somewhere else.

    The transport was compared against a string literal in the agent runtime, in the
    image dispatcher, in Settings.credential and in the credentials store, so adding a
    provider meant editing four files that had no reason to know about each other. A
    provider is one row here now.
    """
    id: str
    label: str
    env_key: str
    base_url: str = ''          # empty keeps the OpenAI client's own default
    # The Responses API is an OpenAI endpoint; every compatible gateway speaks Chat
    # Completions instead.
    use_responses: bool = True
    image_url: str = ''


OPENAI = Provider('openai', 'OpenAI', 'OPENAI_API_KEY')
NVIDIA = Provider('nvidia', 'NVIDIA', 'NVIDIA_API_KEY', NVIDIA_TEXT_URL,
                  use_responses=False, image_url=NVIDIA_IMAGE_URL)
HUGGINGFACE = Provider('huggingface', 'Hugging Face', 'HF_TOKEN', HUGGINGFACE_TEXT_URL,
                       use_responses=False)
# Self-hosted, like the Qwen-Image-Edit NIM the reference editor already talks to:
# Qwen-Image-2.1 is served by no Inference Provider, so the endpoint is yours.
QWEN = Provider('qwen', 'Qwen (auto-hospedado)', 'QWEN_IMAGE_API_KEY',
                use_responses=False, image_url='')

PROVIDERS = {provider.id: provider for provider in (OPENAI, NVIDIA, HUGGINGFACE, QWEN)}


def provider_for(name):
    provider = PROVIDERS.get(name)
    if provider is None:
        raise ValueError(f'Provedor desconhecido: {name}')
    return provider

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

# Qwen-Image-2.1 documents support for up to ten reference images.
QWEN_IMAGE_REFERENCES = 10
# It draws at seven fixed resolutions and nothing else, exactly like FLUX draws only on
# its own grid. The studio's 4:5 feed and its 1536x800 landscape have no match here, so
# those exports are refused rather than upscaled from a smaller frame.
QWEN_IMAGE_BOXES = ((2048, 2048), (2400, 1792), (1792, 2400), (2528, 1696),
                    (1696, 2528), (2752, 1536), (1536, 2752))
QWEN_IMAGE_STEPS = 40
# The refusal message names publication formats, because that is what the person
# choosing in the form sees; the model's own grid means nothing to them.
QWEN_INSTAGRAM_FORMATS = ('feed quadrado 1080x1080, feed alto 3:4 1080x1440 '
                          'e story 1080x1920')


@dataclass(frozen=True)
class ModelOption:
    id: str
    label: str
    provider: str
    model: str
    note: str = ''
    # Image capabilities. A text-to-image renderer never sees product, logo or brand
    # references, so the prompt must not claim they were attached.
    accepts_references: bool = True
    max_prompt_chars: int = OPENAI_IMAGE_PROMPT_CHARS
    max_references: int = OPENAI_IMAGE_REFERENCES
    # Body fields this model needs on every request. Measured, not guessed: a model that
    # reasons by default spends the whole output budget thinking and answers nothing.
    extra_body: dict | None = None
    # Some gateways cap the completion at a low default and still report
    # finish_reason='stop', so a truncated object arrives looking complete.
    max_output_tokens: int | None = None

    def public(self, available):
        return {'id': self.id, 'label': self.label, 'provider': self.provider,
                'model': self.model, 'note': self.note, 'available': available,
                'accepts_references': self.accepts_references}


# Both of these were measured against build.nvidia.com and found unable to delegate:
# with tools alone the model answers finish_reason='tool_calls', and adding
# response_format json_schema silently drops every tool call. That used to disqualify
# them, because the Director orchestrated through tools. The pipeline now walks the
# specialists itself and no agent is given a tool, so a provider that refuses the
# combination no longer refuses a campaign.
NEMOTRON_ULTRA = ModelOption(
    'nvidia:nvidia/nemotron-3-ultra-550b-a55b', 'Nemotron 3 Ultra · NVIDIA', 'nvidia',
    'nvidia/nemotron-3-ultra-550b-a55b')

KIMI_K3 = ModelOption('nvidia:moonshotai/kimi-k3', 'Kimi K3 · NVIDIA', 'nvidia',
                      'moonshotai/kimi-k3')
FLUX_DEV = ModelOption('nvidia:black-forest-labs/flux.1-dev', 'FLUX.1 dev · NVIDIA', 'nvidia',
                       'black-forest-labs/flux.1-dev',
                       'Comparativo de arte. Sem referências de marca e apenas no feed quadrado.',
                       accepts_references=False, max_prompt_chars=FLUX_PROMPT_CHARS,
                       max_references=0)

# Routed through the Hugging Face gateway, which pins the inference provider in the id.
# Leaving it on the default ':fastest' policy would let the same id land on a different
# backend between runs, and a capability measured once would prove nothing.
# Both halves of this id were measured against the live gateway, not read off a card.
#
# The provider is pinned to DeepInfra because Novita wraps the answer in a JSON array —
# `[{...}]` where the schema demands an object — on every setting tried, which fails
# strict validation before the pipeline can use it. DeepInfra returns the object.
#
# Thinking is switched off because Qwen ships it on at reasoning_effort xhigh and
# recommends budgeting 262k tokens for reasoning alone. Left on, the model spends the
# whole completion budget deliberating and returns empty content: measured at 0 usable
# tokens on DeepInfra and OVHcloud, and a 504 from the gateway on a full campaign.
#
# The ceiling is explicit because DeepInfra otherwise cuts the answer at roughly 400
# tokens and still returns finish_reason='stop': the JSON arrives truncated mid-string,
# which reads as a malformed model rather than a clipped response.
QWEN_TEXT = ModelOption('huggingface:Qwen/Qwen3.8-27B:deepinfra', 'Qwen3.8 27B · Hugging Face',
                        'huggingface', 'Qwen/Qwen3.8-27B:deepinfra',
                        'Modelo aberto roteado pela Hugging Face; exige HF_TOKEN.',
                        extra_body={'chat_template_kwargs': {'enable_thinking': False}},
                        max_output_tokens=8000)

# Qwen-Image-2.1 is served by no Inference Provider — the model card says so and ships a
# Diffusers snippet for a local GPU. It is offered here against an endpoint you host,
# the same arrangement the reference editor already uses for Qwen-Image-Edit, and stays
# unavailable until QWEN_IMAGE_URL is set.
QWEN_IMAGE = ModelOption('qwen:Qwen/Qwen-Image-2.1', 'Qwen-Image 2.1 · auto-hospedado',
                         'qwen', 'Qwen/Qwen-Image-2.1',
                         'Endpoint próprio: defina QWEN_IMAGE_URL. Aceita até 10 referências, '
                         'em sete proporções fixas; o feed 4:5 e o 1536x800 não cabem.',
                         max_references=QWEN_IMAGE_REFERENCES)


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
    """Keep the configured default first; other providers require explicit selection."""
    options = [default_text(settings)] if settings.model else []
    options.extend((NEMOTRON_ULTRA, KIMI_K3, QWEN_TEXT))
    return options


def image_models(settings):
    options = [default_image(settings)] if settings.image_model else []
    options.extend((FLUX_DEV, QWEN_IMAGE))
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


def qwen_canvas(width, height):
    """Smallest documented Qwen-Image box matching the export ratio without upscaling.

    Returns None when no ratio fits, and the caller refuses the run — the same contract
    flux_canvas has, for the same reason: enlarging pixels the model never drew is a
    silent quality loss dressed up as a success.
    """
    target = width / height
    candidates = [(w, h) for w, h in QWEN_IMAGE_BOXES
                  if abs(w / h / target - 1) <= .02 and w >= width and h >= height]
    return min(candidates, key=lambda box: box[0] * box[1]) if candidates else None
