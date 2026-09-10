import os
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_root: Path
    api_key: SecretStr = SecretStr("")
    model: str = ""
    image_model: str = "gpt-image-2"
    max_turns: int = Field(default=12, ge=4, le=30)
    timeout_seconds: int = Field(default=180, ge=1, le=3600)

    @classmethod
    def load(cls, root: Path):
        from .paths import AppPaths
        root = AppPaths.discover(root).data_root
        values = {**dotenv_values(root / ".env"), **os.environ}
        return cls(
            project_root=root,
            api_key=values.get("OPENAI_API_KEY") or "",
            model=values.get("OPENAI_MODEL") or "",
            image_model=values.get("OPENAI_IMAGE_MODEL") or "gpt-image-2",
            max_turns=values.get("MAX_TURNS", 12),
            timeout_seconds=values.get("REQUEST_TIMEOUT_SECONDS", 180),
        )

    def validate_live(self):
        if not self.api_key.get_secret_value().strip() or not self.model.strip():
            raise ValueError("Preencha OPENAI_API_KEY e OPENAI_MODEL no .env para execução live")
