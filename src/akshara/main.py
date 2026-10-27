from contextlib import asynccontextmanager
from typing import Annotated

import uvicorn
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from akshara import __version__
from akshara.config import get_settings
from akshara.ocr import (
    OCRBusyError,
    OCRInputError,
    OCRResponse,
    OCRService,
    OCRUnavailableError,
)
from akshara.security import ApiKeyMiddleware, RequestSizeLimitMiddleware

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(app.state.ocr_service.probe)
    yield


app = FastAPI(
    title="Akshara",
    description="From text to understanding.",
    version=__version__,
    lifespan=lifespan,
)
app.state.ocr_service = OCRService(settings)
app.add_middleware(
    RequestSizeLimitMiddleware,
    max_bytes=settings.max_file_size_mb * 1024 * 1024 + 64 * 1024,
)
app.add_middleware(ApiKeyMiddleware, api_key=settings.api_key.get_secret_value())


@app.get("/")
def root() -> dict:
    return {
        "name": "Akshara",
        "name_native": "अक्षर",
        "version": __version__,
        "tagline": "From text to understanding.",
        "features": {
            "ocr": True,
            "llm": settings.enable_llm,
        },
    }


@app.get("/health")
def health(request: Request) -> dict[str, str | bool]:
    ready = request.app.state.ocr_service.ready
    return {"status": "ok" if ready else "degraded", "paddleocr": ready}


@app.post("/v1/ocr", response_model=OCRResponse, response_model_exclude_none=True)
async def ocr(
    request: Request,
    file: Annotated[UploadFile, File()],
    language: Annotated[str | None, Query()] = None,
    page_details: Annotated[bool, Query()] = False,
    extraction_source: Annotated[bool, Query()] = False,
    coordinates: Annotated[bool, Query()] = False,
) -> OCRResponse:
    selected_language = (language or settings.enabled_ocr_languages[0]).lower()
    if selected_language not in settings.enabled_ocr_languages:
        raise HTTPException(
            status_code=422,
            detail=f"Language must be one of: {', '.join(settings.enabled_ocr_languages)}",
        )

    try:
        if not file.size:
            raise OCRInputError("Uploaded file is empty")
        if file.size > settings.max_file_size_mb * 1024 * 1024:
            raise OCRInputError("File exceeds the configured size limit", 413)
        data = await file.read(settings.max_file_size_mb * 1024 * 1024 + 1)
        if len(data) > settings.max_file_size_mb * 1024 * 1024:
            raise OCRInputError("File exceeds the configured size limit", 413)
        return await request.app.state.ocr_service.process(
            data,
            file.content_type,
            selected_language,
            page_details,
            extraction_source,
            coordinates,
        )
    except OCRInputError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except OCRBusyError as exc:
        raise HTTPException(status_code=429, detail="OCR service is busy") from exc
    except OCRUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="PaddleOCR is not available"
        ) from exc
    finally:
        await file.close()


def run() -> None:
    uvicorn.run(
        "akshara.main:app",
        host=settings.hostname if settings.hostname else "0.0.0.0",
        port=settings.port if settings.port else 8080,
        reload=True,
    )
