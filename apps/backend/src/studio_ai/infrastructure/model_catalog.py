"""Models the studio can run, and the endpoint each one needs.

One vocabulary shared by the dropdown, the agent runtime and the image backend.
Ids carry their provider ('openai:', 'nvidia:') because the same slug can exist
on more than one endpoint, and 'demo' stays a first-class option so the UI can
offer offline fixtures next to the real models.

Ids are stable: saved campaigns and drafts store them. Labels are what a person reads in
the form, so they carry the model's own name only; the provider is exposed separately
and the form groups options by it.

Each image option also declares what its renderer can take, so the prompt
builder never describes inputs the provider will not receive and never applies
one provider's request limits to another.
"""
import re
from dataclasses import dataclass

NVIDIA_TEXT_URL = 'https://integrate.api.nvidia.com/v1'
# One token reaches hundreds of open models. The endpoint is a drop-in replacement for
# the OpenAI client, and it speaks Chat Completions only, like NVIDIA NIM.
HUGGINGFACE_TEXT_URL = 'https://router.huggingface.co/v1'
# Image generation does not go through the OpenAI-compatible endpoint, which is chat only.
# The router proxies each inference provider under its own prefix instead; the official
# huggingface_hub client builds this exact base for fal when the key is an HF token.
HUGGINGFACE_FAL_URL = 'https://router.huggingface.co/fal-ai'

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
    # A server someone runs themselves. What makes it usable is its address, not a key:
    # the key is optional, and a model offered without an address can only fail.
    self_hosted: bool = False
    url_env: str = ''


OPENAI = Provider('openai', 'OpenAI', 'OPENAI_API_KEY')
NVIDIA = Provider('nvidia', 'NVIDIA', 'NVIDIA_API_KEY', NVIDIA_TEXT_URL, use_responses=False)
HUGGINGFACE = Provider('huggingface', 'Hugging Face', 'HF_TOKEN', HUGGINGFACE_TEXT_URL,
                       use_responses=False, image_url=HUGGINGFACE_FAL_URL)
# Self-hosted, like the Qwen-Image-Edit NIM the reference editor already talks to:
# Qwen-Image-2.1 is served by no Inference Provider, so the endpoint is yours.
QWEN = Provider('qwen', 'Qwen (auto-hospedado)', 'QWEN_IMAGE_API_KEY',
                use_responses=False, self_hosted=True, url_env='QWEN_IMAGE_URL')
# This machine's GPU, through scripts/zimage_server.py. Free to run: the cost is the
# hardware and the time, not a provider's bill.
LOCAL = Provider('local', 'Na sua máquina', 'LOCAL_IMAGE_TOKEN',
                 use_responses=False, self_hosted=True, url_env='LOCAL_IMAGE_URL')

PROVIDERS = {provider.id: provider for provider in (OPENAI, NVIDIA, HUGGINGFACE, QWEN, LOCAL)}


def provider_for(name):
    provider = PROVIDERS.get(name)
    if provider is None:
        raise ValueError(f'Provedor desconhecido: {name}')
    return provider


# https://developers.openai.com/api/reference/resources/images/methods/edit
OPENAI_IMAGE_PROMPT_CHARS = 32_000
OPENAI_IMAGE_REFERENCES = 16

# Qwen-Image-2.1 documents support for up to ten reference images.
QWEN_IMAGE_REFERENCES = 10
# It draws at seven fixed resolutions and nothing else. The studio's 4:5 feed and its
# 1536x800 landscape have no match here, so those exports are refused rather than
# upscaled from a smaller frame.
QWEN_IMAGE_BOXES = ((2048, 2048), (2400, 1792), (1792, 2400), (2528, 1696),
                    (1696, 2528), (2752, 1536), (1536, 2752))
QWEN_IMAGE_STEPS = 40
# The refusal message names publication formats, because that is what the person
# choosing in the form sees; the model's own grid means nothing to them.
QWEN_INSTAGRAM_FORMATS = ('feed quadrado 1080x1080, feed alto 3:4 1080x1440 '
                          'e story 1080x1920')

# Z-Image draws any aspect ratio inside a pixel-area band, per the model card: 512x512 to
# 2048x2048 in total area. The pipeline floors each side to a multiple of 16, and the
# studio's working canvases already are, so every publication preset fits as it stands.
ZIMAGE_MIN_AREA = 512 * 512
ZIMAGE_MAX_AREA = 2048 * 2048
ZIMAGE_SIDE_STEP = 16
# The text encoder is cut at 512 tokens (max_sequence_length in ZImagePipeline) and
# truncates silently, so a full Brand Kit dump would push the headline out of a prompt
# that still "succeeds". The curated short brief stays well inside the limit.
ZIMAGE_PROMPT_CHARS = 1_500
# Sampling as the model cards specify. Turbo is distilled: 9 steps are 8 transformer
# passes, and guidance must be 0. The base model wants 28-50 steps and 3-5 guidance.
ZIMAGE_PARAMS = {
    'fal-ai/z-image/turbo': {'num_inference_steps': 9, 'guidance_scale': 0.0},
    'fal-ai/z-image/base': {'num_inference_steps': 30, 'guidance_scale': 4.0},
}


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
        provider = PROVIDERS.get(self.provider)
        return {'id': self.id, 'label': self.label, 'provider': self.provider,
                'provider_label': provider.label if provider else self.provider,
                'model': self.model, 'note': self.note, 'available': available,
                'accepts_references': self.accepts_references}


def display_name(slug):
    """The name a person reads for an OpenAI slug, keeping the slug itself untouched.

    `gpt-6-luna` reads as GPT-6 Luna and `gpt-image-2` as GPT Image 2. Anything that is
    not a GPT slug is returned as it came, rather than guessed at.
    """
    if not slug:
        return 'OpenAI'
    parts = slug.split('-')
    if parts[0] != 'gpt' or len(parts) < 2:
        return slug
    words = [part.capitalize() for part in parts[2:]]
    if re.fullmatch(r'\d+(\.\d+)?', parts[1]):
        return ' '.join([f'GPT-{parts[1]}', *words])
    return ' '.join(['GPT', parts[1].capitalize(), *words])


# Both of these were measured against build.nvidia.com and found unable to delegate:
# with tools alone the model answers finish_reason='tool_calls', and adding
# response_format json_schema silently drops every tool call. That used to disqualify
# them, because the Director orchestrated through tools. The pipeline now walks the
# specialists itself and no agent is given a tool, so a provider that refuses the
# combination no longer refuses a campaign.
NEMOTRON_ULTRA = ModelOption(
    'nvidia:nvidia/nemotron-3-ultra-550b-a55b', 'NVIDIA Nemotron 3 Ultra', 'nvidia',
    'nvidia/nemotron-3-ultra-550b-a55b')

KIMI_K3 = ModelOption('nvidia:moonshotai/kimi-k3', 'Kimi K3', 'nvidia', 'moonshotai/kimi-k3')

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
QWEN_TEXT = ModelOption('huggingface:Qwen/Qwen3.8-27B:deepinfra', 'Qwen3.8 27B',
                        'huggingface', 'Qwen/Qwen3.8-27B:deepinfra',
                        'Modelo aberto roteado pela Hugging Face; exige HF_TOKEN.',
                        extra_body={'chat_template_kwargs': {'enable_thinking': False}},
                        max_output_tokens=8000)

# Qwen-Image-2.1 is served by no Inference Provider — the model card says so and ships a
# Diffusers snippet for a local GPU. It is offered here against an endpoint you host,
# the same arrangement the reference editor already uses for Qwen-Image-Edit, and stays
# unavailable until QWEN_IMAGE_URL is set.
QWEN_IMAGE = ModelOption('qwen:Qwen/Qwen-Image-2.1', 'Qwen-Image 2.1',
                         'qwen', 'Qwen/Qwen-Image-2.1',
                         'Endpoint próprio: defina QWEN_IMAGE_URL. Aceita até 10 referências, '
                         'em sete proporções fixas; o feed 4:5 e o 1536x800 não cabem.',
                         max_references=QWEN_IMAGE_REFERENCES)

# Tongyi-MAI's Z-Image, served by fal through the Hugging Face router. The mapping from
# repository to provider id was read from the Hub API (inferenceProviderMapping), both
# live. The catalog id keeps the repository name; `model` is what goes in the URL.
#
# Text-to-image only: no product photo, logo or brand reference reaches it. What it does
# bring is every publication format, including the 4:5 feed the fixed-grid models refuse,
# and the Turbo card singles out accurate Chinese and English text inside the image.
ZIMAGE_NOTE = ('Sem foto do produto nem referências de marca: gera só a partir do texto. '
               'Aceita todos os formatos, inclusive o feed 4:5. Exige HF_TOKEN.')
Z_IMAGE_TURBO = ModelOption('huggingface:Tongyi-MAI/Z-Image-Turbo', 'Z-Image Turbo',
                            'huggingface', 'fal-ai/z-image/turbo', ZIMAGE_NOTE,
                            accepts_references=False, max_prompt_chars=ZIMAGE_PROMPT_CHARS,
                            max_references=0)
Z_IMAGE = ModelOption('huggingface:Tongyi-MAI/Z-Image', 'Z-Image',
                      'huggingface', 'fal-ai/z-image/base', ZIMAGE_NOTE,
                      accepts_references=False, max_prompt_chars=ZIMAGE_PROMPT_CHARS,
                      max_references=0)

# The same Turbo model on this machine's GPU. Same limits as the hosted one, because
# they are the model's, not the host's; slower on a consumer card, and free per image.
Z_IMAGE_TURBO_LOCAL = ModelOption(
    'local:Tongyi-MAI/Z-Image-Turbo', 'Z-Image Turbo', 'local', 'Tongyi-MAI/Z-Image-Turbo',
    'Roda na GPU desta máquina, sem custo por imagem e mais devagar. Sem foto do produto '
    'nem referências de marca. Exige o servidor ligado e LOCAL_IMAGE_URL.',
    accepts_references=False, max_prompt_chars=ZIMAGE_PROMPT_CHARS, max_references=0)


def default_text(settings):
    """The .env model stays the default even when unset, so an unconfigured
    server still fails with the original OPENAI_API_KEY/OPENAI_MODEL message."""
    return ModelOption('openai:' + settings.model, display_name(settings.model),
                       'openai', settings.model, 'Modelo do .env')


def default_image(settings):
    return ModelOption('openai:' + settings.image_model, display_name(settings.image_model),
                       'openai', settings.image_model,
                       'Padrão: usa foto do produto, logo e brand kit')


def text_models(settings):
    """Keep the configured default first; other providers require explicit selection."""
    options = [default_text(settings)] if settings.model else []
    options.extend((NEMOTRON_ULTRA, KIMI_K3, QWEN_TEXT))
    return options


def image_models(settings):
    options = [default_image(settings)] if settings.image_model else []
    options.extend((Z_IMAGE_TURBO, Z_IMAGE, Z_IMAGE_TURBO_LOCAL, QWEN_IMAGE))
    return options


def find(options, model_id):
    return next((option for option in options if option.id == model_id), None)


def resolve_text(settings, model_id):
    """None means 'whatever the .env configures', preserving previous behaviour."""
    return default_text(settings) if not model_id else find(text_models(settings), model_id)


def resolve_image(settings, model_id):
    return default_image(settings) if not model_id else find(image_models(settings), model_id)


def qwen_canvas(width, height):
    """Smallest documented Qwen-Image box matching the export ratio without upscaling.

    Returns None when no ratio fits, and the caller refuses the run: enlarging pixels
    the model never drew is a silent quality loss dressed up as a success.
    """
    target = width / height
    candidates = [(w, h) for w, h in QWEN_IMAGE_BOXES
                  if abs(w / h / target - 1) <= .02 and w >= width and h >= height]
    return min(candidates, key=lambda box: box[0] * box[1]) if candidates else None


def zimage_canvas(native, width, height):
    """The working canvas for Z-Image, or None when no valid one exists.

    The studio's native canvas already matches the export ratio, is at least as large
    as the export and has sides in multiples of 16. It is used as it stands when its
    area sits inside the model's band; otherwise the run is refused rather than bent.
    """
    w, h = (int(value) for value in native.split('x'))
    if w < width or h < height or w % ZIMAGE_SIDE_STEP or h % ZIMAGE_SIDE_STEP:
        return None
    if not ZIMAGE_MIN_AREA <= w * h <= ZIMAGE_MAX_AREA:
        return None
    return w, h
