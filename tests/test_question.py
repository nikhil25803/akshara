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


class FakeModel:
    def __init__(self) -> None:
        self.content = json.dumps({"answer": "Charles Dickens"})
        self.calls: list[dict[str, Any]] = []
        self.error: Exception | None = None

    def create_chat_completion(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"choices": [{"message": {"content": self.content}}]}


def image_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (10, 10), "white").save(output, format="PNG")
    return output.getvalue()


def post_question(
    client: TestClient,
    question: str = "Who wrote this quote?",
    headers: dict[str, str] | None = None,
):
    return client.post(
        "/v1/ocr/ask",
        headers=AUTH_HEADERS if headers is None else headers,
        files={
            "file": ("document.png", image_bytes(), "image/png"),
            "question": (None, question),
        },
    )


@pytest.fixture
def question_client(
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


def test_question_returns_grounded_answer(
    question_client: tuple[TestClient, FakeModel],
) -> None:
    client, model = question_client

    response = post_question(client)

    assert response.status_code == 200
    assert response.json() == {"answer": "Charles Dickens"}
    call = model.calls[0]
    assert call["temperature"] == 0.0
    assert call["response_format"] == {
        "type": "json_object",
        "schema": {
            "type": "object",
            "properties": {"answer": {"type": ["string", "null"]}},
            "required": ["answer"],
            "additionalProperties": False,
        },
    }
    assert "Who wrote this quote?" in call["messages"][1]["content"]
    assert "Hello Akshara" in call["messages"][1]["content"]


def test_question_returns_null_when_answer_is_absent(
    question_client: tuple[TestClient, FakeModel],
) -> None:
    client, model = question_client
    model.content = json.dumps({"answer": None})

    assert post_question(client).json() == {"answer": None}


@pytest.mark.parametrize("question", ["", "   ", "é" * 2049])
def test_invalid_questions_are_rejected(
    question_client: tuple[TestClient, FakeModel], question: str
) -> None:
    client, _ = question_client

    assert post_question(client, question).status_code == 422


def test_question_requires_authentication(client: TestClient) -> None:
    assert post_question(client, headers={}).status_code == 401


def test_disabled_llm_rejects_questions(client: TestClient) -> None:
    assert post_question(client).status_code == 503


def test_question_endpoint_uses_request_size_limit(client: TestClient) -> None:
    response = client.post(
        "/v1/ocr/ask",
        headers={
            **AUTH_HEADERS,
            "content-length": str(settings.max_file_size_mb * 1024 * 1024 + 65 * 1024),
        },
    )

    assert response.status_code == 413


def test_empty_ocr_text_cannot_be_answered(
    question_client: tuple[TestClient, FakeModel],
) -> None:
    client, _ = question_client
    service = OCRService(
        settings, engine_factory=lambda _: FakeEngine(""), runtime_probe=lambda: True
    )
    service.probe()
    app.state.ocr_service = service

    response = post_question(client)

    assert response.status_code == 422
    assert response.json() == {"detail": "OCR produced no text to answer from"}


def test_busy_llm_rejects_questions(
    question_client: tuple[TestClient, FakeModel],
) -> None:
    client, _ = question_client
    service = app.state.llm_service
    assert service._lock.acquire(blocking=False)
    try:
        assert post_question(client).status_code == 429
    finally:
        service._lock.release()


@pytest.mark.parametrize(
    "content",
    [
        "{}",
        '{"answer":42}',
        '{"answer":"   "}',
    ],
)
def test_invalid_question_output_returns_502(
    question_client: tuple[TestClient, FakeModel], content: str
) -> None:
    client, model = question_client
    model.content = content

    assert post_question(client).status_code == 502


def test_question_context_overflow_returns_413(
    question_client: tuple[TestClient, FakeModel],
) -> None:
    client, model = question_client
    model.error = ValueError("context size exceeded")

    assert post_question(client).status_code == 413
    assert app.state.llm_service.ready is True


def test_question_runtime_failure_degrades_llm(
    question_client: tuple[TestClient, FakeModel],
) -> None:
    client, model = question_client
    model.error = RuntimeError("inference failed")

    assert post_question(client).status_code == 503
    assert client.get("/health").json() == {
        "status": "degraded",
        "paddleocr": True,
        "llama_cpp": False,
    }
