from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from akshara.config import get_settings
from akshara.helpers.ocr import (
    OCRBusyError,
    OCRInputError,
    OCRResponse,
    OCRUnavailableError,
)

router = APIRouter()


@router.post("/v1/ocr", response_model=OCRResponse, response_model_exclude_none=True)
async def ocr(
    request: Request,
    file: Annotated[UploadFile, File()],
    language: Annotated[str | None, Query()] = None,
    page_details: Annotated[bool, Query()] = False,
    extraction_source: Annotated[bool, Query()] = False,
    coordinates: Annotated[bool, Query()] = False,
) -> OCRResponse:
    settings = get_settings()
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
