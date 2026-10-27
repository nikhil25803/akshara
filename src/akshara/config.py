from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SUPPORTED_OCR_LANGUAGES = frozenset(
    {
        "abq",
        "af",
        "ang",
        "ar",
        "ava",
        "az",
        "be",
        "bg",
        "bgc",
        "bh",
        "bho",
        "bs",
        "ch",
        "che",
        "chinese_cht",
        "cs",
        "cy",
        "da",
        "dar",
        "de",
        "en",
        "es",
        "et",
        "fa",
        "fr",
        "ga",
        "gom",
        "hi",
        "hr",
        "hu",
        "id",
        "inh",
        "is",
        "it",
        "japan",
        "ka",
        "kbd",
        "korean",
        "ku",
        "la",
        "lbe",
        "lez",
        "lt",
        "lv",
        "mah",
        "mai",
        "mi",
        "mn",
        "mr",
        "ms",
        "mt",
        "ne",
        "new",
        "nl",
        "no",
        "oc",
        "pi",
        "pl",
        "pt",
        "ro",
        "rs_cyrillic",
        "rs_latin",
        "ru",
        "sa",
        "sck",
        "sk",
        "sl",
        "sq",
        "sv",
        "sw",
        "tab",
        "ta",
        "te",
        "tl",
        "tr",
        "ug",
        "uk",
        "ur",
        "uz",
        "vi",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    hostname: str = "0.0.0.0"
    port: int = 8080
    api_key: SecretStr = Field(min_length=32)

    ocr_engine: str = "paddleocr"
    ocr_languages: str = "en,hi"
    ocr_max_concurrent_requests: int = Field(default=1, ge=1)

    enable_llm: bool = False
    llm_backend: str = "llama_cpp"
    llm_model_path: Path = Path("./models/model.gguf")
    llm_device: Literal["cpu", "gpu", "auto"] = "cpu"

    max_file_size_mb: int = Field(default=25, ge=1)
    max_pdf_pages: int = Field(default=50, ge=1)
    max_image_pixels: int = Field(default=25_000_000, ge=1)

    @field_validator("ocr_languages")
    @classmethod
    def validate_ocr_languages(cls, value: str) -> str:
        languages = tuple(
            dict.fromkeys(
                item.strip().lower() for item in value.split(",") if item.strip()
            )
        )
        if not languages:
            raise ValueError("OCR_LANGUAGES must contain at least one language")
        unsupported = sorted(set(languages) - SUPPORTED_OCR_LANGUAGES)
        if unsupported:
            raise ValueError(f"Unsupported OCR languages: {', '.join(unsupported)}")
        return ",".join(languages)

    @property
    def enabled_ocr_languages(self) -> tuple[str, ...]:
        return tuple(self.ocr_languages.split(","))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
