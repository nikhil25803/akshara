from __future__ import annotations

import importlib
import os
import threading
import warnings
from collections.abc import Callable
from io import BytesIO
from typing import Any, Literal

import numpy as np
import pymupdf as fitz
from fastapi.concurrency import run_in_threadpool
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from akshara.config import Settings

PDF_DPI = 150
SUPPORTED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png"}

# PaddleOCR otherwise contacts model hosts during import, before a model is requested.
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


class OCRInputError(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        self.detail = detail
        self.status_code = status_code


class OCRUnavailableError(Exception):
    pass


class OCRBusyError(Exception):
    pass


class OCRBlock(BaseModel):
    text: str
    confidence: float | None = None
    coordinates: list[list[float]] = Field(min_length=4, max_length=4)


class OCRPage(BaseModel):
    page_number: int
    text: str | None = None
    extraction_source: Literal["embedded_text", "paddleocr"] | None = None
    blocks: list[OCRBlock] | None = None


class OCRResponse(BaseModel):
    text: str
    language: str
    mime_type: Literal["application/pdf", "image/jpeg", "image/png"]
    page_count: int
    warnings: list[str]
    pages: list[OCRPage] | None = None


class OCRService:
    def __init__(
        self,
        settings: Settings,
        engine_factory: Callable[[str], Any] | None = None,
        runtime_probe: Callable[[], bool] | None = None,
    ) -> None:
        self.settings = settings
        self._engine_factory = engine_factory or self._create_engine
        self._runtime_probe = runtime_probe or self._probe_runtime
        self._engines: dict[str, Any] = {}
        self._engine_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(settings.ocr_max_concurrent_requests)
        self.runtime_installed = False
        self.ready = False

    def probe(self) -> None:
        try:
            self.runtime_installed = self._runtime_probe()
        except Exception:  # noqa: BLE001 - readiness must survive any broken native runtime
            self.runtime_installed = False
        self.ready = self.runtime_installed

    @staticmethod
    def _probe_runtime() -> bool:
        paddle = importlib.import_module("paddle")
        importlib.import_module("paddleocr")
        paddle.utils.run_check()
        return True

    @staticmethod
    def _create_engine(language: str) -> Any:
        from paddleocr import PaddleOCR

        return PaddleOCR(
            lang=language,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device="cpu",
        )

    def _get_engine(self, language: str) -> Any:
        with self._engine_lock:
            if language not in self._engines:
                self._engines[language] = self._engine_factory(language)
            return self._engines[language]

    async def process(
        self,
        data: bytes,
        declared_mime_type: str | None,
        language: str,
        page_details: bool,
        extraction_source: bool,
        coordinates: bool,
    ) -> OCRResponse:
        if not self.runtime_installed:
            raise OCRUnavailableError
        if not self._slots.acquire(blocking=False):
            raise OCRBusyError
        try:
            return await run_in_threadpool(
                self._process,
                data,
                declared_mime_type,
                language,
                page_details,
                extraction_source,
                coordinates,
            )
        finally:
            self._slots.release()

    def _process(
        self,
        data: bytes,
        declared_mime_type: str | None,
        language: str,
        page_details: bool,
        extraction_source: bool,
        coordinates: bool,
    ) -> OCRResponse:
        mime_type = self._detect_mime_type(data)
        self._validate_declared_mime_type(declared_mime_type, mime_type)

        try:
            pages, page_warnings = (
                self._process_pdf(data, language, coordinates)
                if mime_type == "application/pdf"
                else self._process_image(data, language, coordinates)
            )
            self.ready = True
        except OCRInputError:
            raise
        except Exception as exc:
            self.ready = False
            with self._engine_lock:
                self._engines.pop(language, None)
            raise OCRUnavailableError from exc

        include_pages = page_details or extraction_source or coordinates
        response_pages = None
        if include_pages:
            response_pages = [
                OCRPage(
                    page_number=page["page_number"],
                    text=page["text"] if page_details else None,
                    extraction_source=page["source"] if extraction_source else None,
                    blocks=page["blocks"] if coordinates else None,
                )
                for page in pages
            ]

        return OCRResponse(
            text="\n\n".join(page["text"] for page in pages if page["text"]),
            language=language,
            mime_type=mime_type,
            page_count=len(pages),
            warnings=page_warnings,
            pages=response_pages,
        )

    @staticmethod
    def _detect_mime_type(data: bytes) -> str:
        if b"%PDF-" in data[:1024]:
            return "application/pdf"
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as image:
                    if image.format == "JPEG":
                        return "image/jpeg"
                    if image.format == "PNG":
                        return "image/png"
        except (
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            UnidentifiedImageError,
            OSError,
        ):
            pass
        raise OCRInputError("Unsupported or invalid file content", 415)

    @staticmethod
    def _validate_declared_mime_type(declared: str | None, detected: str) -> None:
        if not declared:
            return
        declared = declared.partition(";")[0].strip().lower()
        if declared == "application/octet-stream":
            return
        if declared not in SUPPORTED_MIME_TYPES or declared != detected:
            raise OCRInputError("Declared MIME type does not match file content", 415)

    def _open_image(self, data: bytes) -> Image.Image:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image = Image.open(BytesIO(data))
                if image.format not in {"JPEG", "PNG"}:
                    raise OCRInputError("Only JPEG and PNG images are supported", 415)
                if getattr(image, "n_frames", 1) != 1:
                    raise OCRInputError("Multi-frame images are not supported")
                if image.width * image.height > self.settings.max_image_pixels:
                    raise OCRInputError("Image exceeds the configured pixel limit", 413)
                image.load()
                return image.convert("RGB")
        except OCRInputError:
            raise
        except (
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            UnidentifiedImageError,
            OSError,
        ) as exc:
            raise OCRInputError("Invalid image") from exc

    def _process_image(
        self, data: bytes, language: str, coordinates: bool
    ) -> tuple[list[dict[str, Any]], list[str]]:
        image = self._open_image(data)
        try:
            text, blocks = self._run_ocr(image, language, coordinates)
        finally:
            image.close()
        warnings_list = [] if text else ["No text detected on page 1"]
        return [
            {"page_number": 1, "text": text, "source": "paddleocr", "blocks": blocks}
        ], warnings_list

    def _process_pdf(
        self, data: bytes, language: str, coordinates: bool
    ) -> tuple[list[dict[str, Any]], list[str]]:
        try:
            document = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise OCRInputError("Invalid PDF") from exc

        try:
            if document.needs_pass:
                raise OCRInputError("Encrypted PDFs are not supported")
            if document.page_count == 0:
                raise OCRInputError("PDF contains no pages")
            if document.page_count > self.settings.max_pdf_pages:
                raise OCRInputError("PDF exceeds the configured page limit", 413)

            pages: list[dict[str, Any]] = []
            warnings_list: list[str] = []
            scale = PDF_DPI / 72
            for page_number, page in enumerate(document, start=1):
                width = page.rect.width * scale
                height = page.rect.height * scale
                if (
                    width <= 0
                    or height <= 0
                    or width * height > self.settings.max_image_pixels
                ):
                    raise OCRInputError(
                        f"PDF page {page_number} exceeds the configured pixel limit",
                        413,
                    )

                text = page.get_text("text", sort=True).strip()
                if text:
                    blocks = self._pdf_blocks(page) if coordinates else []
                    source = "embedded_text"
                else:
                    pixmap = page.get_pixmap(
                        matrix=fitz.Matrix(scale, scale),
                        colorspace=fitz.csRGB,
                        alpha=False,
                    )
                    image = Image.frombytes(
                        "RGB", (pixmap.width, pixmap.height), pixmap.samples
                    )
                    try:
                        text, blocks = self._run_ocr(image, language, coordinates)
                    finally:
                        image.close()
                    source = "paddleocr"

                if not text:
                    warnings_list.append(f"No text detected on page {page_number}")
                pages.append(
                    {
                        "page_number": page_number,
                        "text": text,
                        "source": source,
                        "blocks": blocks,
                    }
                )
            return pages, warnings_list
        finally:
            document.close()

    @staticmethod
    def _pdf_blocks(page: fitz.Page) -> list[OCRBlock]:
        width, height = page.rect.width, page.rect.height
        return [
            OCRBlock(
                text=word[4],
                coordinates=[
                    [word[0] / width, word[1] / height],
                    [word[2] / width, word[1] / height],
                    [word[2] / width, word[3] / height],
                    [word[0] / width, word[3] / height],
                ],
            )
            for word in page.get_text("words", sort=True)
            if word[4].strip()
        ]

    def _run_ocr(
        self, image: Image.Image, language: str, coordinates: bool
    ) -> tuple[str, list[OCRBlock]]:
        engine = self._get_engine(language)
        texts: list[str] = []
        blocks: list[OCRBlock] = []
        for result in engine.predict(np.asarray(image)):
            result_json = result.json() if callable(result.json) else result.json
            values = result_json.get("res", result_json)
            result_texts = values.get("rec_texts", [])
            texts.extend(text for text in result_texts if text)
            if coordinates:
                scores = values.get("rec_scores", [])
                polygons = values.get("rec_polys", [])
                for text, score, polygon in zip(
                    result_texts, scores, polygons, strict=False
                ):
                    if text:
                        blocks.append(
                            OCRBlock(
                                text=text,
                                confidence=float(score),
                                coordinates=[
                                    [float(x) / image.width, float(y) / image.height]
                                    for x, y in polygon
                                ],
                            )
                        )
        return "\n".join(texts), blocks
