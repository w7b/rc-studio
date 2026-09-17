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

from realcenter_marketing.infrastructure.model_catalog import FLUX_SIDES, FLUX_STEPS, flux_canvas

FLUX_MAX_SIDE = max(FLUX_SIDES)


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


class NvidiaFlux:
    def __init__(self, option, *, api_key, base_url, timeout):
        self.option = option
        self.api_key, self.base_url, self.timeout = api_key, base_url, timeout

    def canvas(self, native, width, height):
        box = flux_canvas(width, height)
        if box is None:
            raise ImageBackendError(
                f'{self.option.label} desenha no máximo {FLUX_MAX_SIDE} px por lado, em '
                f'proporções fixas; a exportação {width}x{height} exigiria ampliar a imagem. '
                'Use o feed quadrado (1080x1080) para comparar as artes.')
        return f'{box[0]}x{box[1]}'

    def render(self, prompt, size, references, *, client=None):
        width, height = (int(value) for value in size.split('x'))
        payload = {'prompt': prompt, 'width': width, 'height': height,
                   'steps': FLUX_STEPS, 'cfg_scale': 3.5, 'mode': 'base'}
        request = urllib.request.Request(
            self.base_url.rstrip('/') + '/' + self.option.model,
            data=json.dumps(payload).encode('utf-8'), method='POST',
            headers={'Authorization': 'Bearer ' + self.api_key,
                     'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            raise ImageBackendError(
                f'{self.option.label} recusou a requisição ({exc.code}): ' + _detail(exc)) from None
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise ImageBackendError(f'Falha ao chamar {self.option.label}: {exc}') from None
        artifacts = body.get('artifacts') or []
        if not artifacts or not artifacts[0].get('base64'):
            raise ImageBackendError(f'{self.option.label} não retornou uma imagem')
        artifact = artifacts[0]
        # A filtered artifact still carries base64 — a black frame. Saving it would
        # publish an empty art as if the run had succeeded.
        reason = str(artifact.get('finishReason') or '').upper()
        if reason and reason != 'SUCCESS':
            raise ImageBackendError(
                f'{self.option.label} bloqueou a geração ({reason}). Revise o texto do '
                'briefing e da headline antes de repetir.')
        raw = base64.b64decode(artifact['base64'], validate=True)
        # FLUX answers in JPEG; the studio stores and validates PNG everywhere else.
        with Image.open(io.BytesIO(raw)) as drawn:
            drawn.load()
            buffer = io.BytesIO()
            drawn.convert('RGB').save(buffer, format='PNG')
        usage = {'provider': 'nvidia', 'model': self.option.model, 'steps': FLUX_STEPS,
                 'seed': artifact.get('seed'), 'finish_reason': artifact.get('finishReason')}
        return buffer.getvalue(), usage


def backend_for(option, *, api_key='', base_url='', timeout=600) -> ImageBackend:
    if option.provider == 'nvidia':
        return NvidiaFlux(option, api_key=api_key, base_url=base_url, timeout=timeout)
    return OpenAIImages(option)


def _detail(error):
    try:
        return error.read().decode('utf-8', 'replace')[:400]
    except OSError:
        return str(error.reason or '')
