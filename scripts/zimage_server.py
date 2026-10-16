"""Z-Image Turbo on this machine's GPU, behind a small HTTP endpoint the studio calls.

Runs outside Docker, in its own virtualenv, because it needs the host GPU. The studio
reaches it at LOCAL_IMAGE_URL (http://host.docker.internal:8001/generate from a
container). Set up once with scripts/setup_zimage.ps1, then:

    %USERPROFILE%\\.studio-ai\\zimage\\Scripts\\python.exe scripts\\zimage_server.py

Defaults target an 8 GB card: the 4-bit build of the model, and CPU offload so only the
component in use sits on the GPU. Environment overrides:

    ZIMAGE_MODEL        repository to load (default unsloth/Z-Image-Turbo-unsloth-bnb-4bit)
    ZIMAGE_DTYPE        bfloat16 | float16 (default bfloat16, the dtype it was trained in)
    ZIMAGE_OFFLOAD      model | sequential | none (default model)
    ZIMAGE_HOST/PORT    bind address (default 127.0.0.1:8001)
    LOCAL_IMAGE_TOKEN   shared secret; when set, requests must carry it as a Bearer token
"""
import base64
import hmac
import io
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = os.environ.get('ZIMAGE_MODEL', 'unsloth/Z-Image-Turbo-unsloth-bnb-4bit')
DTYPE = os.environ.get('ZIMAGE_DTYPE', 'bfloat16')
OFFLOAD = os.environ.get('ZIMAGE_OFFLOAD', 'model')
HOST = os.environ.get('ZIMAGE_HOST', '127.0.0.1')
PORT = int(os.environ.get('ZIMAGE_PORT', '8001'))
TOKEN = os.environ.get('LOCAL_IMAGE_TOKEN', '').strip()

# The model card's band: 512x512 to 2048x2048 in total area, sides floored to 16.
MIN_AREA, MAX_AREA, SIDE_STEP = 512 * 512, 2048 * 2048, 16
MAX_PROMPT = 4000
MAX_BODY = 64 * 1024

_gpu = threading.Lock()
_pipe = None
_state = {'busy': False, 'loaded_at': None, 'generated': 0}


def load():
    """Load once at start: a failure here is a setup problem and should stop the server,
    not surface later as a timeout inside a campaign."""
    global _pipe
    import torch
    from diffusers import ZImagePipeline

    if not torch.cuda.is_available():
        raise SystemExit('Nenhuma GPU CUDA disponível para o PyTorch deste ambiente.')
    dtype = {'bfloat16': torch.bfloat16, 'float16': torch.float16}[DTYPE]
    print(f'Carregando {MODEL} em {DTYPE} na {torch.cuda.get_device_name(0)}...', flush=True)
    started = time.time()
    pipe = ZImagePipeline.from_pretrained(MODEL, torch_dtype=dtype)
    if OFFLOAD == 'model':
        pipe.enable_model_cpu_offload()
    elif OFFLOAD == 'sequential':
        pipe.enable_sequential_cpu_offload()
    else:
        pipe.to('cuda')
    _pipe = pipe
    _state['loaded_at'] = time.time()
    print(f'Pronto em {time.time() - started:.0f}s. Escutando em http://{HOST}:{PORT}', flush=True)


def generate(prompt, width, height, steps, guidance, seed):
    import torch

    generator = torch.Generator('cpu').manual_seed(seed)
    started = time.time()
    with _gpu:
        _state['busy'] = True
        try:
            image = _pipe(prompt=prompt, width=width, height=height, num_inference_steps=steps,
                          guidance_scale=guidance, generator=generator).images[0]
        finally:
            _state['busy'] = False
            torch.cuda.empty_cache()
    # A numeric overflow in the wrong dtype comes out as a uniformly black frame. It is
    # a failed render, and must never reach the studio looking like an art.
    low, high = zip(*image.convert('RGB').getextrema())
    if max(high) <= 8:
        raise RuntimeError('A GPU devolveu uma imagem toda preta, sinal de estouro numérico. '
                           'Tente ZIMAGE_DTYPE=float16 ou ZIMAGE_DTYPE=bfloat16.')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    _state['generated'] += 1
    return buffer.getvalue(), time.time() - started


def validar(body):
    prompt = str(body.get('prompt') or '').strip()
    if not prompt:
        raise ValueError('prompt vazio')
    if len(prompt) > MAX_PROMPT:
        raise ValueError(f'prompt acima de {MAX_PROMPT} caracteres')
    width, height = int(body.get('width', 0)), int(body.get('height', 0))
    if width % SIDE_STEP or height % SIDE_STEP:
        raise ValueError(f'largura e altura precisam ser múltiplos de {SIDE_STEP}')
    if not MIN_AREA <= width * height <= MAX_AREA:
        raise ValueError(f'área {width}x{height} fora da faixa do modelo')
    steps = int(body.get('num_inference_steps', 9))
    if not 1 <= steps <= 50:
        raise ValueError('num_inference_steps precisa estar entre 1 e 50')
    guidance = float(body.get('guidance_scale', 0.0))
    seed = int(body.get('seed', int(time.time()) % 2_147_483_647))
    return prompt, width, height, steps, guidance, seed


class Handler(BaseHTTPRequestHandler):
    def _reply(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        if not TOKEN:
            return True
        given = self.headers.get('Authorization', '')
        return hmac.compare_digest(given, f'Bearer {TOKEN}')

    def do_GET(self):
        if self.path != '/health':
            return self._reply(404, {'error': 'rota desconhecida'})
        import torch
        self._reply(200, {'status': 'ok', 'model': MODEL, 'dtype': DTYPE, 'offload': OFFLOAD,
                          'gpu': torch.cuda.get_device_name(0), 'busy': _state['busy'],
                          'generated': _state['generated']})

    def do_POST(self):
        if self.path != '/generate':
            return self._reply(404, {'error': 'rota desconhecida'})
        if not self._authorized():
            return self._reply(401, {'error': 'token ausente ou inválido'})
        length = int(self.headers.get('Content-Length') or 0)
        if length > MAX_BODY:
            return self._reply(413, {'error': 'requisição grande demais'})
        try:
            body = json.loads(self.rfile.read(length) or b'{}')
            prompt, width, height, steps, guidance, seed = validar(body)
        except (ValueError, TypeError) as exc:
            return self._reply(400, {'error': str(exc)})
        try:
            import torch
            content, seconds = generate(prompt, width, height, steps, guidance, seed)
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            return self._reply(507, {'error': 'a GPU ficou sem memória; tente ZIMAGE_OFFLOAD=sequential'})
        except RuntimeError as exc:
            return self._reply(500, {'error': str(exc)})
        self._reply(200, {'image': base64.b64encode(content).decode(), 'seed': seed,
                          'seconds': round(seconds, 1), 'width': width, 'height': height})

    def log_message(self, fmt, *args):
        print(f'{self.address_string()} {fmt % args}', flush=True)


def main():
    if HOST not in ('127.0.0.1', 'localhost') and not TOKEN:
        raise SystemExit('Escutando fora do localhost, defina LOCAL_IMAGE_TOKEN: senão qualquer '
                         'máquina da rede usa sua GPU.')
    load()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == '__main__':
    main()
