from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    ocr_engine: str = "paddleocr"

    enable_llm: bool = False
    llm_backend: str = "llama_cpp"
    llm_model_path: Path = Path("./models/model.gguf")
    llm_device: Literal["cpu", "gpu", "auto"] = "cpu"

    max_file_size_mb: int = Field(default=25, ge=1)
    max_pdf_pages: int = Field(default=50, ge=1)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
