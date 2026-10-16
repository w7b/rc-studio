"""Composition-root alias of the model catalog.

The catalog itself lives in infrastructure so adapters (image backends, prompt
builder) can read model capabilities without importing the composition root.
Bootstrap and tests keep importing from here.
"""
from studio_ai.infrastructure.model_catalog import (  # noqa: F401
    DEMO, HUGGINGFACE_FAL_URL, HUGGINGFACE_TEXT_URL, KIMI_K3, NEMOTRON_ULTRA,
    NVIDIA_TEXT_URL, OPENAI_IMAGE_PROMPT_CHARS, OPENAI_IMAGE_REFERENCES, PROVIDERS,
    QWEN_IMAGE, QWEN_IMAGE_BOXES, QWEN_IMAGE_REFERENCES, QWEN_IMAGE_STEPS, QWEN_TEXT,
    ZIMAGE_MAX_AREA, ZIMAGE_MIN_AREA, ZIMAGE_PARAMS, ZIMAGE_PROMPT_CHARS, Z_IMAGE,
    Z_IMAGE_TURBO, Z_IMAGE_TURBO_LOCAL, ModelOption, Provider, default_image, default_text, display_name, find,
    image_models, provider_for, qwen_canvas, resolve_image, resolve_text, text_models,
    zimage_canvas,
)

__all__ = [
    'DEMO', 'HUGGINGFACE_FAL_URL', 'HUGGINGFACE_TEXT_URL', 'KIMI_K3', 'NEMOTRON_ULTRA',
    'NVIDIA_TEXT_URL', 'OPENAI_IMAGE_PROMPT_CHARS', 'OPENAI_IMAGE_REFERENCES', 'PROVIDERS',
    'QWEN_IMAGE', 'QWEN_IMAGE_BOXES', 'QWEN_IMAGE_REFERENCES', 'QWEN_IMAGE_STEPS', 'QWEN_TEXT',
    'ZIMAGE_MAX_AREA', 'ZIMAGE_MIN_AREA', 'ZIMAGE_PARAMS', 'ZIMAGE_PROMPT_CHARS', 'Z_IMAGE',
    'Z_IMAGE_TURBO', 'Z_IMAGE_TURBO_LOCAL', 'ModelOption', 'Provider', 'default_image', 'default_text',
    'display_name', 'find', 'image_models', 'provider_for', 'qwen_canvas', 'resolve_image',
    'resolve_text', 'text_models', 'zimage_canvas',
]
