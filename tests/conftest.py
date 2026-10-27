import os
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_KEY", "test-api-key-with-at-least-32-characters")

from akshara.helpers.ocr import OCRService
from akshara.main import app, settings

API_KEY = "test-api-key-with-at-least-32-characters"
AUTH_HEADERS = {"api_key": API_KEY}


class FakeResult:
    def __init__(self, width: int, height: int, text: str = "Hello Akshara") -> None:
        self.json = {
            "res": {
                "rec_texts": [text] if text else [],
                "rec_scores": [0.99] if text else [],
                "rec_polys": (
                    [
                        [[0, 0], [width, 0], [width, height], [0, height]],
                    ]
                    if text
                    else []
                ),
            }
        }


class FakeEngine:
    def __init__(self, text: str = "Hello Akshara") -> None:
        self.text = text

    def predict(self, image: Any) -> list[FakeResult]:
        height, width = image.shape[:2]
        return [FakeResult(width, height, self.text)]


@pytest.fixture
def ocr_service() -> tuple[OCRService, list[str]]:
    created_languages: list[str] = []

    def create_engine(language: str) -> FakeEngine:
        created_languages.append(language)
        return FakeEngine()

    service = OCRService(
        settings, engine_factory=create_engine, runtime_probe=lambda: True
    )
    return service, created_languages


@pytest.fixture
def client(ocr_service: tuple[OCRService, list[str]]) -> Iterator[TestClient]:
    previous_service = app.state.ocr_service
    app.state.ocr_service = ocr_service[0]
    with TestClient(app) as test_client:
        deadline = time.monotonic() + 1
        while not ocr_service[0].ready and time.monotonic() < deadline:
            time.sleep(0.001)
        assert ocr_service[0].ready
        yield test_client
    app.state.ocr_service = previous_service
