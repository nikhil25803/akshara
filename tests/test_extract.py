import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from conftest import AUTH_HEADERS
from fastapi.testclient import TestClient
from test_ocr import image_bytes

from akshara.config import Settings
from akshara.helpers.extraction import LLMService, parse_template
from akshara.main import app, settings


class FakeModel:
    def __init__(self, *responses: str, tokens: int = 1) -> None:
        self.responses = list(responses)
        self.tokens = tokens
        self.calls = 0
        self.metadata = {"tokenizer.chat_template": "test-template"}

    def tokenize(self, _content: bytes, add_bos: bool = True) -> list[int]:
        return list(range(self.tokens))

    def create_chat_completion(self, **_kwargs: Any) -> dict[str, Any]:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return {"choices": [{"message": {"content": response}}]}


@pytest.fixture
def llm_service(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[LLMService, FakeModel]]:
    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(b"test")
    monkeypatch.setattr(settings, "enable_llm", True)
    monkeypatch.setattr(settings, "llm_model_path", model_path)
    model = FakeModel('{"response":{"answer":"Hello"}}')
    service = LLMService(settings, model_factory=lambda _: model)
    service.probe()
    previous_service = app.state.llm_service
    app.state.llm_service = service
    yield service, model
    app.state.llm_service = previous_service


def post_extract(
    client: TestClient,
    prompt: str = "Extract the answer",
    template: str | None = None,
    query: str = "",
):
    data = {"prompt": prompt}
    if template is not None:
        data["template"] = template
    return client.post(
        f"/v1/extract{query}",
        headers=AUTH_HEADERS,
        data=data,
        files={"file": ("document.png", image_bytes(), "image/png")},
    )


def test_extract_without_template_returns_model_object(
    client: TestClient, llm_service: tuple[LLMService, FakeModel]
) -> None:
    response = post_extract(client)

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "response": {"answer": "Hello"},
        "warnings": [],
    }


def test_nested_template_arrays_nulls_and_verified_evidence(
    client: TestClient, llm_service: tuple[LLMService, FakeModel]
) -> None:
    llm_service[1].responses = [
        json.dumps(
            {
                "response": {
                    "licence_number": "A1",
                    "holder": {"name": 42, "ignored": "value"},
                    "expiry_date": "not-a-date",
                    "classes": [{"code": "LMV"}],
                },
                "evidence": [
                    {
                        "path": "/licence_number",
                        "text": "Hello Akshara",
                        "page": 1,
                    },
                    {"path": "/classes/0/code", "text": "invented", "page": 1},
                ],
            }
        )
    ]
    template = json.dumps(
        {
            "licence_number": "string",
            "holder": {"name": "string"},
            "expiry_date": "date",
            "classes": [{"code": "string"}],
        }
    )

    response = post_extract(client, template=template, query="?evidence=true")

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == {
        "licence_number": "A1",
        "holder": {"name": None},
        "expiry_date": None,
        "classes": [{"code": "LMV"}],
    }
    assert body["evidence"] == {"/licence_number": {"text": "Hello Akshara", "page": 1}}
    assert "No valid value for /holder/name" in body["warnings"]
    assert "No valid value for /expiry_date" in body["warnings"]
    assert "No verified evidence for /classes/0/code" in body["warnings"]


def test_invalid_model_output_is_retried_once(
    client: TestClient, llm_service: tuple[LLMService, FakeModel]
) -> None:
    llm_service[1].responses = ["not-json", '{"response":{"answer":"retry"}}']

    response = post_extract(client)

    assert response.status_code == 200
    assert response.json()["response"] == {"answer": "retry"}
    assert llm_service[1].calls == 2


def test_invalid_model_output_returns_502(
    client: TestClient, llm_service: tuple[LLMService, FakeModel]
) -> None:
    llm_service[1].responses = ["not-json"]

    assert post_extract(client).status_code == 502
    assert llm_service[1].calls == 2


@pytest.mark.parametrize(
    "template",
    [
        "not-json",
        "{}",
        '{"field":"unknown"}',
        '{"items":[]}',
        '{"items":["string","number"]}',
    ],
)
def test_invalid_templates_return_422(
    client: TestClient,
    llm_service: tuple[LLMService, FakeModel],
    template: str,
) -> None:
    assert post_extract(client, template=template).status_code == 422


def test_template_depth_and_field_limits() -> None:
    nested: dict[str, Any] = {"value": "string"}
    for _ in range(8):
        nested = {"nested": nested}
    with pytest.raises(ValueError, match="nesting depth"):
        parse_template(json.dumps(nested))

    fields = {f"field_{index}": "string" for index in range(101)}
    with pytest.raises(ValueError, match="100-field"):
        parse_template(json.dumps(fields))


def test_context_limit_returns_413(
    client: TestClient, llm_service: tuple[LLMService, FakeModel], monkeypatch
) -> None:
    llm_service[1].tokens = 300
    monkeypatch.setattr(settings, "llm_context_size", 512)
    monkeypatch.setattr(settings, "llm_max_output_tokens", 1)

    assert post_extract(client).status_code == 413


def test_busy_and_unavailable_llm_return_safe_errors(
    client: TestClient, llm_service: tuple[LLMService, FakeModel], monkeypatch
) -> None:
    service = llm_service[0]
    assert service._slots.acquire(blocking=False)
    try:
        assert post_extract(client).status_code == 429
    finally:
        service._slots.release()

    monkeypatch.setattr(settings, "enable_llm", False)
    response = post_extract(client)
    assert response.status_code == 503
    assert response.json() == {"detail": "LLM is not available"}


def test_extract_uses_shared_language_validation(
    client: TestClient, llm_service: tuple[LLMService, FakeModel]
) -> None:
    assert post_extract(client, query="?language=fr").status_code == 422


def test_extract_uses_streaming_request_limit(
    client: TestClient, llm_service: tuple[LLMService, FakeModel]
) -> None:
    response = client.post(
        "/v1/extract",
        headers={
            **AUTH_HEADERS,
            "content-length": str(settings.max_file_size_mb * 1024 * 1024 + 65 * 1024),
        },
    )

    assert response.status_code == 413


def test_llm_probe_requires_enabled_existing_model(tmp_path: Path) -> None:
    config = Settings(
        api_key="test-api-key-with-at-least-32-characters",
        enable_llm=True,
        llm_model_path=tmp_path / "missing.gguf",
        _env_file=None,
    )
    service = LLMService(config, model_factory=lambda _: FakeModel("{}"))

    service.probe()

    assert service.ready is False
    assert service._model is None


def test_llm_probe_requires_chat_template(tmp_path: Path) -> None:
    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(b"test")
    config = Settings(
        api_key="test-api-key-with-at-least-32-characters",
        enable_llm=True,
        llm_model_path=model_path,
        _env_file=None,
    )
    model = FakeModel("{}")
    model.metadata = {}
    service = LLMService(config, model_factory=lambda _: model)

    service.probe()

    assert service.ready is False


def test_health_reflects_enabled_llm_readiness(
    client: TestClient, llm_service: tuple[LLMService, FakeModel]
) -> None:
    assert client.get("/health").json() == {
        "status": "ok",
        "paddleocr": True,
        "llama_cpp": True,
    }

    llm_service[0].ready = False
    assert client.get("/health").json() == {
        "status": "degraded",
        "paddleocr": True,
        "llama_cpp": False,
    }
