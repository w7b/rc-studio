import os
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from .model_catalog import NVIDIA_IMAGE_URL, NVIDIA_TEXT_URL, PROVIDERS, provider_for

PROVIDER_KEYS = {name: provider.env_key for name, provider in PROVIDERS.items()}


def platform_values(env_root):
    return {**dotenv_values(Path(env_root) / '.env'), **os.environ}


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_root: Path
    api_key: SecretStr = SecretStr("")
    nvidia_api_key: SecretStr = SecretStr("")
    nvidia_base_url: str = NVIDIA_TEXT_URL
    nvidia_image_url: str = NVIDIA_IMAGE_URL
    model: str = ""
    image_model: str = "gpt-image-2"
    # Credentials and endpoints for providers beyond the two that predate the registry.
    # api_key and nvidia_api_key stay as their own fields because callers assign to them.
    keys: dict[str, SecretStr] = Field(default_factory=dict)
    endpoints: dict[str, str] = Field(default_factory=dict)
    max_turns: int = Field(default=12, ge=4, le=30)
    timeout_seconds: int = Field(default=4800, ge=1, le=14400)
    # Ceiling for a single agent. The run-wide timeout cannot tell a slow model
    # from a stuck one: a Copywriter call was measured at 15 minutes before
    # failing on malformed output, with nothing on screen the whole time.
    agent_timeout_seconds: int = Field(default=600, ge=30, le=4800)

    @classmethod
    def load(cls, root: Path, *, env_root: Path | None = None):
        """Credentials come from env_root, never from the tenant's own data root."""
        from .paths import AppPaths
        paths = AppPaths.discover(root)
        root = paths.data_root
        secrets_root = Path(env_root).resolve() if env_root is not None else paths.env_root
        values = platform_values(secrets_root)
        from realcenter_marketing.infrastructure.model_credentials import load
        overrides = load(secrets_root, root)
        for provider, key in overrides.items():
            values[PROVIDER_KEYS[provider]] = key
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
            agent_timeout_seconds=values.get("AGENT_TIMEOUT_SECONDS", 600),
            keys={name: SecretStr(values.get(provider.env_key) or "")
                  for name, provider in PROVIDERS.items()},
            endpoints={**{name: (values.get(f"{name.upper()}_BASE_URL") or "").strip()
                          for name in PROVIDERS},
                       "qwen_image": (values.get("QWEN_IMAGE_URL") or "").strip()},
        )

    def credential(self, provider):
        name = getattr(provider, 'id', provider)
        legacy = {'openai': self.api_key, 'nvidia': self.nvidia_api_key}
        secret = legacy[name] if name in legacy else self.keys.get(name, SecretStr(''))
        return secret.get_secret_value().strip()

    def base_url_for(self, provider):
        """An operator may repoint a gateway; the catalog default stands otherwise."""
        if provider.id == 'nvidia':
            return self.nvidia_base_url
        return (self.endpoints.get(provider.id) or provider.base_url).strip()

    def image_url_for(self, provider):
        if provider.id == 'nvidia':
            return self.nvidia_image_url
        return (self.endpoints.get(f'{provider.id}_image') or provider.image_url).strip()

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
