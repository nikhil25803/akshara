import os
from io import BytesIO

import pymupdf as fitz
import pytest
from conftest import AUTH_HEADERS, FakeEngine
from fastapi.testclient import TestClient
from PIL import Image

from akshara.main import app, settings
from akshara.ocr import OCRService


def test_model_source_check_is_disabled_at_startup() -> None:
    assert os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] == "True"


def image_bytes(size: tuple[int, int] = (10, 10), image_format: str = "PNG") -> bytes:
    output = BytesIO()
    Image.new("RGB", size, "white").save(output, format=image_format)
    return output.getvalue()


def pdf_bytes(
    text: str | None = None, pages: int = 1, encrypted: bool = False
) -> bytes:
    document = fitz.open()
    for _ in range(pages):
        page = document.new_page(width=200, height=200)
        if text:
            page.insert_text((20, 40), text)
    options = {}
    if encrypted:
        options = {
            "encryption": fitz.PDF_ENCRYPT_AES_256,
            "owner_pw": "owner-password",
            "user_pw": "user-password",
        }
    data = document.tobytes(**options)
    document.close()
    return data


def post_file(
    client: TestClient,
    data: bytes,
    mime_type: str,
    query: str = "",
    headers: dict[str, str] | None = None,
):
    return client.post(
        f"/v1/ocr{query}",
        headers=AUTH_HEADERS if headers is None else headers,
        files={"file": ("document", data, mime_type)},
    )


def test_authentication_is_required_except_for_root_and_health(
    client: TestClient,
) -> None:
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get("/docs").status_code == 401
    assert post_file(client, image_bytes(), "image/png", headers={}).status_code == 401
    assert (
        post_file(
            client, image_bytes(), "image/png", headers={"api_key": "wrong"}
        ).status_code
        == 401
    )


def test_compact_image_response_uses_default_language(client: TestClient) -> None:
    response = post_file(client, image_bytes(), "image/png")

    assert response.status_code == 200
    assert response.json() == {
        "text": "Hello Akshara",
        "language": "en",
        "mime_type": "image/png",
        "page_count": 1,
        "warnings": [],
    }


def test_all_optional_details(client: TestClient) -> None:
    response = post_file(
        client,
        image_bytes(),
        "image/png",
        "?page_details=true&extraction_source=true&coordinates=true",
    )

    assert response.status_code == 200
    page = response.json()["pages"][0]
    assert page["page_number"] == 1
    assert page["text"] == "Hello Akshara"
    assert page["extraction_source"] == "paddleocr"
    assert page["blocks"][0] == {
        "text": "Hello Akshara",
        "confidence": 0.99,
        "coordinates": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
    }


@pytest.mark.parametrize(
    ("query", "expected_keys"),
    [
        ("?page_details=true", {"page_number", "text"}),
        ("?extraction_source=true", {"page_number", "extraction_source"}),
        ("?coordinates=true", {"page_number", "blocks"}),
    ],
)
def test_each_detail_flag_is_independent(
    client: TestClient, query: str, expected_keys: set[str]
) -> None:
    response = post_file(client, image_bytes(), "image/png", query)

    assert response.status_code == 200
    assert set(response.json()["pages"][0]) == expected_keys


def test_language_must_be_enabled(
    client: TestClient,
    ocr_service: tuple[OCRService, list[str]],
) -> None:
    assert (
        post_file(client, image_bytes(), "image/png", "?language=hi").json()["language"]
        == "hi"
    )
    assert (
        post_file(client, image_bytes(), "image/png", "?language=fr").status_code == 422
    )

    post_file(client, image_bytes(), "image/png", "?language=en")
    post_file(client, image_bytes(), "image/png", "?language=en")
    assert ocr_service[1] == ["hi", "en"]


def test_embedded_pdf_text_skips_ocr(
    client: TestClient, ocr_service: tuple[OCRService, list[str]]
) -> None:
    response = post_file(
        client,
        pdf_bytes("Embedded text"),
        "application/pdf",
        "?page_details=true&extraction_source=true&coordinates=true",
    )

    assert response.status_code == 200
    body = response.json()
    assert "Embedded text" in body["text"]
    assert body["pages"][0]["extraction_source"] == "embedded_text"
    assert "confidence" not in body["pages"][0]["blocks"][0]
    assert ocr_service[1] == []


def test_blank_pdf_uses_ocr(client: TestClient) -> None:
    response = post_file(
        client,
        pdf_bytes(),
        "application/pdf",
        "?extraction_source=true",
    )

    assert response.status_code == 200
    assert response.json()["pages"][0]["extraction_source"] == "paddleocr"


@pytest.mark.parametrize(
    ("data", "mime_type", "status_code"),
    [
        (b"plain text", "text/plain", 415),
        (b"%PDF-not-a-pdf", "application/pdf", 400),
        (image_bytes(), "image/jpeg", 415),
        (b"", "image/png", 400),
    ],
)
def test_invalid_uploads(
    client: TestClient, data: bytes, mime_type: str, status_code: int
) -> None:
    assert post_file(client, data, mime_type).status_code == status_code


def test_encrypted_pdf_is_rejected(client: TestClient) -> None:
    assert (
        post_file(client, pdf_bytes(encrypted=True), "application/pdf").status_code
        == 400
    )


def test_file_size_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "max_file_size_mb", 1)

    assert (
        post_file(
            client, b"x" * (1024 * 1024 + 1), "application/octet-stream"
        ).status_code
        == 413
    )


def test_content_length_limit(client: TestClient) -> None:
    response = client.post(
        "/v1/ocr",
        headers={
            **AUTH_HEADERS,
            "content-length": str(settings.max_file_size_mb * 1024 * 1024 + 65 * 1024),
        },
    )

    assert response.status_code == 413


def test_image_pixel_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "max_image_pixels", 50)

    assert post_file(client, image_bytes((10, 10)), "image/png").status_code == 413


def test_pdf_page_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "max_pdf_pages", 1)

    assert post_file(client, pdf_bytes(pages=2), "application/pdf").status_code == 413


def test_empty_ocr_result_returns_warning(client: TestClient) -> None:
    service = OCRService(
        settings, engine_factory=lambda _: FakeEngine(""), runtime_probe=lambda: True
    )
    app.state.ocr_service = service
    service.probe()

    response = post_file(client, image_bytes(), "image/png")

    assert response.status_code == 200
    assert response.json()["text"] == ""
    assert response.json()["warnings"] == ["No text detected on page 1"]


def test_degraded_runtime_returns_503(client: TestClient) -> None:
    service = OCRService(settings, runtime_probe=lambda: False)
    app.state.ocr_service = service
    service.probe()

    assert client.get("/health").json() == {"status": "degraded", "paddleocr": False}
    assert post_file(client, image_bytes(), "image/png").status_code == 503


def test_busy_runtime_returns_429(
    client: TestClient, ocr_service: tuple[OCRService, list[str]]
) -> None:
    service = ocr_service[0]
    assert service._slots.acquire(blocking=False)
    try:
        assert post_file(client, image_bytes(), "image/png").status_code == 429
    finally:
        service._slots.release()
