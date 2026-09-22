"""Composition-root alias of the model catalog.

The catalog itself lives in infrastructure so adapters (image backends, prompt
builder) can read model capabilities without importing the composition root.
Bootstrap and tests keep importing from here.
"""
from realcenter_marketing.infrastructure.model_catalog import (  # noqa: F401
    DEMO, FLUX_DEV, FLUX_SIDES, FLUX_STEPS, HUGGINGFACE_TEXT_URL, KIMI_K3,
    NVIDIA_IMAGE_URL, NVIDIA_TEXT_URL, NEMOTRON_ULTRA, OPENAI_IMAGE_PROMPT_CHARS,
    OPENAI_IMAGE_REFERENCES, PROVIDERS, QWEN_IMAGE, QWEN_IMAGE_BOXES,
    QWEN_IMAGE_REFERENCES, QWEN_IMAGE_STEPS, QWEN_TEXT,
    ModelOption, Provider, default_image, default_text, find, flux_canvas, image_models,
    provider_for, qwen_canvas, resolve_image, resolve_text, text_models,
)

__all__ = [
    'DEMO', 'FLUX_DEV', 'FLUX_SIDES', 'FLUX_STEPS', 'HUGGINGFACE_TEXT_URL', 'KIMI_K3',
    'NVIDIA_IMAGE_URL', 'NVIDIA_TEXT_URL', 'NEMOTRON_ULTRA', 'OPENAI_IMAGE_PROMPT_CHARS',
    'OPENAI_IMAGE_REFERENCES', 'PROVIDERS', 'QWEN_IMAGE', 'QWEN_IMAGE_BOXES',
    'QWEN_IMAGE_REFERENCES', 'QWEN_IMAGE_STEPS', 'QWEN_TEXT',
    'ModelOption', 'Provider', 'default_image', 'default_text', 'find', 'flux_canvas',
    'image_models', 'provider_for', 'qwen_canvas', 'resolve_image', 'resolve_text',
    'text_models',
]
