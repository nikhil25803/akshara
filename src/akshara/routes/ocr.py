from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from akshara.config import get_settings
from akshara.helpers.ocr import (
    OCRBusyError,
    OCRInputError,
    OCRResponse,
    OCRUnavailableError,
    read_upload,
    select_ocr_language,
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
    try:
        selected_language = select_ocr_language(settings, language)
        data = await read_upload(file, settings.max_file_size_mb)
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
