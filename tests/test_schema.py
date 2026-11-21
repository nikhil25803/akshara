import json
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from conftest import AUTH_HEADERS, FakeEngine
from fastapi.testclient import TestClient
from PIL import Image

from akshara.helpers.llm import LLMService
from akshara.helpers.ocr import OCRService
from akshara.main import app, settings

SCHEMA = {
    "type": "object",
    "properties": {
        "issue_date": {"type": "string"},
        "date_of_expiry": {"type": "string"},
    },
    "required": ["issue_date", "date_of_expiry"],
    "additionalProperties": False,
}
EXPECTED = {"issue_date": "02/02/2010", "date_of_expiry": "01/02/2030"}
COMPANIES_SCHEMA = {
    "type": "object",
    "properties": {"companies": {"type": "array", "items": {"type": "string"}}},
    "required": ["companies"],
    "additionalProperties": False,
}


class FakeModel:
    def __init__(self, content: str | None = None) -> None:
        self.content = content or json.dumps(EXPECTED)
        self.calls: list[dict[str, Any]] = []
        self.fail = False

    def create_chat_completion(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("inference failed")
        return {"choices": [{"message": {"content": self.content}}]}


def image_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (10, 10), "white").save(output, format="PNG")
    return output.getvalue()


def post_schema(client: TestClient, schema: str = json.dumps(SCHEMA)):
    return client.post(
        "/v1/ocr/schema",
        headers=AUTH_HEADERS,
        files={
            "file": ("document.png", image_bytes(), "image/png"),
            "schema": (None, schema),
        },
    )


@pytest.fixture
def schema_client(
    tmp_path: Path,
    ocr_service: tuple[OCRService, list[str]],
) -> Iterator[tuple[TestClient, FakeModel]]:
    model_path = tmp_path / "model.gguf"
    model_path.touch()
    model = FakeModel()
    llm_service = LLMService(settings, model_factory=lambda **_: model)

    previous_enable_llm = settings.enable_llm
    previous_model_path = settings.llm_model_path
    previous_ocr_service = app.state.ocr_service
    previous_llm_service = app.state.llm_service
    settings.enable_llm = True
    settings.llm_model_path = model_path
    app.state.ocr_service = ocr_service[0]
    app.state.llm_service = llm_service
    try:
        with TestClient(app) as client:
            yield client, model
    finally:
        settings.enable_llm = previous_enable_llm
        settings.llm_model_path = previous_model_path
        app.state.ocr_service = previous_ocr_service
        app.state.llm_service = previous_llm_service


def test_schema_extraction_returns_only_structured_data(
    schema_client: tuple[TestClient, FakeModel],
) -> None:
    client, model = schema_client

    response = post_schema(client)

    assert response.status_code == 200
    assert response.json() == EXPECTED
    assert model.calls[0]["temperature"] == 0.0
    assert model.calls[0]["response_format"] == {
        "type": "json_object",
        "schema": SCHEMA,
    }
    assert "Hello Akshara" in model.calls[0]["messages"][1]["content"]


def test_enabled_health_includes_llama_cpp(
    schema_client: tuple[TestClient, FakeModel],
) -> None:
    client, _ = schema_client

    assert client.get("/health").json() == {
        "status": "ok",
        "paddleocr": True,
        "llama_cpp": True,
    }


def test_schema_extraction_supports_array_fields(
    schema_client: tuple[TestClient, FakeModel],
) -> None:
    client, model = schema_client
    expected = {"companies": ["Cautio", "Mswasth Tech Pvt Ltd."]}
    model.content = json.dumps(expected)

    response = post_schema(client, json.dumps(COMPANIES_SCHEMA))

    assert response.status_code == 200
    assert response.json() == expected


def test_disabled_llm_returns_503(client: TestClient) -> None:
    assert post_schema(client).status_code == 503


def test_schema_endpoint_uses_request_size_limit(client: TestClient) -> None:
    response = client.post(
        "/v1/ocr/schema",
        headers={
            **AUTH_HEADERS,
            "content-length": str(settings.max_file_size_mb * 1024 * 1024 + 65 * 1024),
        },
    )

    assert response.status_code == 413


@pytest.mark.parametrize(
    "schema",
    [
        "not-json",
        '{"type":"array"}',
        '{"type":"object","properties":{"value":{"$ref":"https://example.test"}}}',
    ],
)
def test_invalid_schemas_are_rejected(
    schema_client: tuple[TestClient, FakeModel], schema: str
) -> None:
    client, _ = schema_client

    assert post_schema(client, schema).status_code == 422


def test_empty_ocr_text_is_rejected(
    schema_client: tuple[TestClient, FakeModel],
) -> None:
    client, _ = schema_client
    service = OCRService(
        settings, engine_factory=lambda _: FakeEngine(""), runtime_probe=lambda: True
    )
    service.probe()
    app.state.ocr_service = service

    response = post_schema(client)

    assert response.status_code == 422
    assert response.json() == {"detail": "OCR produced no text to extract"}


def test_busy_llm_returns_429(
    schema_client: tuple[TestClient, FakeModel],
) -> None:
    client, _ = schema_client
    service = app.state.llm_service
    assert service._lock.acquire(blocking=False)
    try:
        assert post_schema(client).status_code == 429
    finally:
        service._lock.release()


def test_invalid_llm_output_returns_502(
    schema_client: tuple[TestClient, FakeModel],
) -> None:
    client, model = schema_client
    model.content = '{"issue_date":"02/02/2010"}'

    assert post_schema(client).status_code == 502


def test_runtime_failure_degrades_llm(
    schema_client: tuple[TestClient, FakeModel],
) -> None:
    client, model = schema_client
    model.fail = True

    assert post_schema(client).status_code == 503
    assert client.get("/health").json() == {
        "status": "degraded",
        "paddleocr": True,
        "llama_cpp": False,
    }
