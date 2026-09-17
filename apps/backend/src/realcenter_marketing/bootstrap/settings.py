import os
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from .model_catalog import NVIDIA_IMAGE_URL, NVIDIA_TEXT_URL

PROVIDER_KEYS = {'openai': 'OPENAI_API_KEY', 'nvidia': 'NVIDIA_API_KEY'}


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_root: Path
    api_key: SecretStr = SecretStr("")
    nvidia_api_key: SecretStr = SecretStr("")
    nvidia_base_url: str = NVIDIA_TEXT_URL
    nvidia_image_url: str = NVIDIA_IMAGE_URL
    model: str = ""
    image_model: str = "gpt-image-2"
    max_turns: int = Field(default=12, ge=4, le=30)
    timeout_seconds: int = Field(default=4800, ge=1, le=14400)

    @classmethod
    def load(cls, root: Path):
        from .paths import AppPaths
        root = AppPaths.discover(root).data_root
        values = {**dotenv_values(root / ".env"), **os.environ}
        return cls(
            project_root=root,
            api_key=values.get("OPENAI_API_KEY") or "",
            nvidia_api_key=values.get("NVIDIA_API_KEY") or "",
            nvidia_base_url=values.get("NVIDIA_BASE_URL") or NVIDIA_TEXT_URL,
            nvidia_image_url=values.get("NVIDIA_IMAGE_URL") or NVIDIA_IMAGE_URL,
            model=values.get("OPENAI_MODEL") or "",
            image_model=values.get("OPENAI_IMAGE_MODEL") or "gpt-image-2",
            max_turns=values.get("MAX_TURNS", 12),
            timeout_seconds=values.get("REQUEST_TIMEOUT_SECONDS", 4800),
        )

    def credential(self, provider):
        secret = self.nvidia_api_key if provider == 'nvidia' else self.api_key
        return secret.get_secret_value().strip()

    def has(self, option):
        return bool(option and option.model and self.credential(option.provider))

    def validate_live(self):
        if not self.api_key.get_secret_value().strip() or not self.model.strip():
            raise ValueError("Preencha OPENAI_API_KEY e OPENAI_MODEL no .env para execução live")

    def validate_provider(self, *options):
        """A model outside OpenAI answers for its own key, not for OPENAI_API_KEY."""
        for option in options:
            if not self.has(option):
                raise ValueError(f"Preencha {PROVIDER_KEYS[option.provider]} no .env para usar {option.label}")
