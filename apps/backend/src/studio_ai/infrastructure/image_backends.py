"""Renderers behind one Protocol, so comparing art measures the model, not the pipeline.

Prompt, brand kit, reference selection and export stay shared in image_generation;
only what turns a prompt into pixels lives here. Capabilities are declared once on
the catalog's ModelOption, so a backend never restates them and the prompt builder
reads the same source.
"""
import base64
import io
import json
import urllib.error
import urllib.request
from typing import Protocol, runtime_checkable

from PIL import Image

from urllib.parse import urlsplit

from studio_ai.infrastructure.model_catalog import (
    QWEN_IMAGE_STEPS, QWEN_INSTAGRAM_FORMATS, ZIMAGE_MAX_AREA, ZIMAGE_MIN_AREA, ZIMAGE_PARAMS,
    qwen_canvas, zimage_canvas)

# A generated image well past this is not an image the studio asked for.
DOWNLOAD_LIMIT = 40 * 1024 * 1024


class ImageBackendError(ValueError):
    """Provider refused the request; the message reaches the operator unchanged."""


@runtime_checkable
class ImageBackend(Protocol):
    option: object

    def canvas(self, native: str, width: int, height: int) -> str:
        """Working canvas for this renderer, in provider terms."""

    def render(self, prompt: str, size: str, references: list, *, client=None):
        """Returns (png_bytes, provider_usage)."""


class OpenAIImages:
    def __init__(self, option):
        self.option = option

    def canvas(self, native, width, height):
        return native

    def render(self, prompt, size, references, *, client=None):
        kwargs = dict(model=self.option.model, prompt=prompt, size=size, quality='medium',
                      output_format='png', n=1)
        response = (client.images.edit(image=references, **kwargs) if references
                    else client.images.generate(**kwargs))
        usage = response.usage.model_dump() if getattr(response, 'usage', None) else None
        if not response.data or not response.data[0].b64_json:
            raise ImageBackendError('A API não retornou uma imagem')
        content = base64.b64decode(response.data[0].b64_json, validate=True)
        if not content.startswith(bytes([0x89]) + b'PNG\r\n' + bytes([0x1a]) + b'\n'):
            raise ImageBackendError('A API não retornou um PNG válido')
        return content, usage


class FalImages:
    """Text-to-image models that fal serves, reached through the Hugging Face router.

    The contract is the one the official huggingface_hub client implements for fal
    (FalAITextToImageTask): POST the prompt with `image_size` as {width, height}, read
    `images[0].url` from the JSON answer, then fetch that URL for the pixels.
    """

    def __init__(self, option, *, api_key, base_url, timeout):
        self.option = option
        self.api_key, self.base_url, self.timeout = api_key, base_url, timeout

    def canvas(self, native, width, height):
        box = zimage_canvas(native, width, height)
        if box is None:
            raise ImageBackendError(
                f'{self.option.label} desenha entre {int(ZIMAGE_MIN_AREA ** .5)}x'
                f'{int(ZIMAGE_MIN_AREA ** .5)} e {int(ZIMAGE_MAX_AREA ** .5)}x'
                f'{int(ZIMAGE_MAX_AREA ** .5)} px de área; a exportação {width}x{height} '
                'não cabe nessa faixa.')
        return f'{box[0]}x{box[1]}'

    def render(self, prompt, size, references, *, client=None):
        if not self.api_key:
            raise ImageBackendError(
                f'{self.option.label} exige HF_TOKEN com permissão para Inference Providers.')
        width, height = (int(value) for value in size.split('x'))
        payload = {'prompt': prompt, 'image_size': {'width': width, 'height': height},
                   **ZIMAGE_PARAMS.get(self.option.model, {})}
        request = urllib.request.Request(
            self.base_url.rstrip('/') + '/' + self.option.model,
            data=json.dumps(payload).encode('utf-8'), method='POST',
            headers={'Authorization': 'Bearer ' + self.api_key,
                     'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            if exc.code == 402:
                raise ImageBackendError(
                    f'{self.option.label}: os créditos da conta Hugging Face acabaram. '
                    'Adicione créditos ou assine o PRO para continuar.') from None
            raise ImageBackendError(
                f'{self.option.label} recusou a requisição ({exc.code}): ' + _detail(exc)) from None
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise ImageBackendError(f'Falha ao chamar {self.option.label}: {exc}') from None

        # A flagged image still comes back as a file, usually blank. Saving it would
        # publish an empty art as if the run had succeeded.
        if any(body.get('has_nsfw_concepts') or []):
            raise ImageBackendError(
                f'{self.option.label} bloqueou a geração pelo filtro de conteúdo. Revise o '
                'texto do briefing e da headline antes de repetir.')
        images = body.get('images') or []
        url = images[0].get('url') if images and isinstance(images[0], dict) else None
        if not url:
            raise ImageBackendError(f'{self.option.label} não retornou uma imagem')
        raw = _download(url, self.timeout, self.option.label)
        # fal answers in JPEG or PNG; the studio stores and validates PNG everywhere else.
        try:
            with Image.open(io.BytesIO(raw)) as drawn:
                drawn.load()
                buffer = io.BytesIO()
                drawn.convert('RGB').save(buffer, format='PNG')
        except OSError:
            raise ImageBackendError(f'{self.option.label} devolveu um arquivo que não é imagem') from None
        usage = {'provider': 'huggingface', 'inference_provider': 'fal-ai',
                 'model': self.option.model, 'seed': body.get('seed'),
                 **ZIMAGE_PARAMS.get(self.option.model, {})}
        return buffer.getvalue(), usage


class QwenImage:
    """Qwen-Image 2.1 on an endpoint you host.

    No Inference Provider serves this model — the card ships a Diffusers snippet for a
    local GPU — so the studio talks to whatever you put behind QWEN_IMAGE_URL, the same
    arrangement the reference editor already uses for Qwen-Image-Edit. Without that
    variable the option is offered but unavailable, never silently routed elsewhere.
    """

    def __init__(self, option, *, api_key, base_url, timeout):
        self.option = option
        self.api_key, self.base_url, self.timeout = api_key, base_url, timeout

    def canvas(self, native, width, height):
        box = qwen_canvas(width, height)
        if box is None:
            # Named in publication formats, not in the model's own grid: the person
            # reading this picks a format in the form, and 2400x1792 tells them nothing.
            raise ImageBackendError(
                f'{self.option.label} não desenha na proporção {width}x{height}. '
                f'Este modelo atende {QWEN_INSTAGRAM_FORMATS}. Escolha um desses '
                'formatos ou gere a arte com outro modelo.')
        return f'{box[0]}x{box[1]}'

    def render(self, prompt, size, references, *, client=None):
        if not self.base_url:
            raise ImageBackendError(
                f'{self.option.label} exige QWEN_IMAGE_URL apontando para o seu endpoint. '
                'Este modelo não é servido por nenhum provedor da Hugging Face.')
        width, height = (int(value) for value in size.split('x'))
        payload = {'prompt': prompt, 'width': width, 'height': height,
                   'num_inference_steps': QWEN_IMAGE_STEPS,
                   'images': [base64.b64encode(item).decode() for item in references or []]}
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if self.api_key:
            headers['Authorization'] = 'Bearer ' + self.api_key
        request = urllib.request.Request(self.base_url, data=json.dumps(payload).encode('utf-8'),
                                         method='POST', headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            raise ImageBackendError(
                f'{self.option.label} recusou a requisição ({exc.code}): ' + _detail(exc)) from None
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise ImageBackendError(f'Falha ao chamar {self.option.label}: {exc}') from None
        encoded = (body.get('images') or [None])[0] or body.get('image')
        if not encoded:
            raise ImageBackendError(f'{self.option.label} não retornou uma imagem')
        raw = base64.b64decode(str(encoded).split(',')[-1], validate=True)
        # The studio stores and validates PNG everywhere else.
        with Image.open(io.BytesIO(raw)) as drawn:
            drawn.load()
            buffer = io.BytesIO()
            drawn.convert('RGB').save(buffer, format='PNG')
        return buffer.getvalue(), {'provider': 'qwen', 'model': self.option.model}


class LocalImages:
    """Z-Image Turbo on this machine's GPU, through scripts/zimage_server.py.

    The server is ours, so the contract is too: width and height as numbers in, the PNG
    back as base64. Nothing leaves the machine. A consumer card takes a while per image,
    and the run's own timeout already covers it.
    """

    def __init__(self, option, *, api_key, base_url, timeout):
        self.option = option
        self.api_key, self.base_url, self.timeout = api_key, base_url, timeout

    def canvas(self, native, width, height):
        return FalImages.canvas(self, native, width, height)

    def render(self, prompt, size, references, *, client=None):
        if not self.base_url:
            raise ImageBackendError(
                f'{self.option.label} (na sua máquina) exige LOCAL_IMAGE_URL e o servidor '
                'scripts/zimage_server.py ligado.')
        width, height = (int(value) for value in size.split('x'))
        payload = {'prompt': prompt, 'width': width, 'height': height,
                   **ZIMAGE_PARAMS['fal-ai/z-image/turbo']}
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if self.api_key:
            headers['Authorization'] = 'Bearer ' + self.api_key
        request = urllib.request.Request(self.base_url, data=json.dumps(payload).encode('utf-8'),
                                         method='POST', headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            raise ImageBackendError(
                f'O servidor local recusou a geração ({exc.code}): ' + _detail(exc)) from None
        except (urllib.error.URLError, ConnectionError) as exc:
            raise ImageBackendError(
                f'O servidor local não respondeu em {self.base_url}. Ligue com '
                'scripts/zimage_server.py e tente de novo.') from None
        except (TimeoutError, ValueError) as exc:
            raise ImageBackendError(f'Falha ao chamar o servidor local: {exc}') from None
        encoded = body.get('image')
        if not encoded:
            raise ImageBackendError('O servidor local não retornou uma imagem')
        try:
            raw = base64.b64decode(encoded, validate=True)
            with Image.open(io.BytesIO(raw)) as drawn:
                drawn.load()
                buffer = io.BytesIO()
                drawn.convert('RGB').save(buffer, format='PNG')
        except (ValueError, OSError):
            raise ImageBackendError('O servidor local devolveu um arquivo que não é imagem') from None
        usage = {'provider': 'local', 'model': self.option.model, 'seed': body.get('seed'),
                 'seconds': body.get('seconds'), **ZIMAGE_PARAMS['fal-ai/z-image/turbo']}
        return buffer.getvalue(), usage


def backend_for(option, *, api_key='', base_url='', timeout=600) -> ImageBackend:
    """An unknown provider used to fall through to OpenAI, which would have sent one
    provider's slug to another provider's endpoint and blamed the model for the error."""
    if option.provider == 'huggingface':
        return FalImages(option, api_key=api_key, base_url=base_url, timeout=timeout)
    if option.provider == 'local':
        return LocalImages(option, api_key=api_key, base_url=base_url, timeout=timeout)
    if option.provider == 'qwen':
        return QwenImage(option, api_key=api_key, base_url=base_url, timeout=timeout)
    if option.provider == 'openai':
        return OpenAIImages(option)
    raise ImageBackendError(f'{option.label} não tem renderizador de imagem neste servidor')


def _detail(error):
    try:
        return error.read().decode('utf-8', 'replace')[:400]
    except OSError:
        return str(error.reason or '')


def _download(url, timeout, label):
    """Fetch the generated file from the provider's media host.

    Only https is followed, and the Hugging Face token is deliberately not sent: the
    media URL is public, and handing a credential to a second host would leak it.
    """
    if urlsplit(url).scheme != 'https':
        raise ImageBackendError(f'{label} devolveu um endereço de imagem inválido')
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as response:
            content = response.read(DOWNLOAD_LIMIT + 1)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise ImageBackendError(f'Falha ao baixar a imagem de {label}: {exc}') from None
    if len(content) > DOWNLOAD_LIMIT:
        raise ImageBackendError(f'{label} devolveu uma imagem maior que o limite aceito')
    return content
