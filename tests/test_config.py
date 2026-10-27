import pytest
from pydantic import ValidationError

from akshara.config import Settings

API_KEY = "test-api-key-with-at-least-32-characters"


def test_languages_are_trimmed_and_deduplicated() -> None:
    settings = Settings(api_key=API_KEY, ocr_languages=" en, hi,en ", _env_file=None)

    assert settings.ocr_languages == "en,hi"
    assert settings.enabled_ocr_languages == ("en", "hi")


@pytest.mark.parametrize("languages", ["", "en,not-a-language"])
def test_invalid_languages_are_rejected(languages: str) -> None:
    with pytest.raises(ValidationError):
        Settings(api_key=API_KEY, ocr_languages=languages, _env_file=None)


def test_api_key_must_be_at_least_32_characters() -> None:
    with pytest.raises(ValidationError):
        Settings(api_key="too-short", _env_file=None)
