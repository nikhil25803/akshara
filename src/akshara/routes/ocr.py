from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from akshara.config import Settings, get_settings
from akshara.helpers.llm import (
    LLMBusyError,
    LLMInputError,
    LLMOutputError,
    LLMUnavailableError,
    parse_json_schema,
    parse_question,
)
from akshara.helpers.ocr import (
    OCRBusyError,
    OCRInputError,
    OCRResponse,
    OCRUnavailableError,
)

router = APIRouter()


class OCRAnswerResponse(BaseModel):
    answer: str | None


def selected_language(settings: Settings, language: str | None) -> str:
    selected = (language or settings.enabled_ocr_languages[0]).lower()
    if selected not in settings.enabled_ocr_languages:
        raise HTTPException(
            status_code=422,
            detail=f"Language must be one of: {', '.join(settings.enabled_ocr_languages)}",
        )
    return selected


async def read_upload(file: UploadFile, settings: Settings) -> bytes:
    if not file.size:
        raise OCRInputError("Uploaded file is empty")
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if file.size > max_bytes:
        raise OCRInputError("File exceeds the configured size limit", 413)
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise OCRInputError("File exceeds the configured size limit", 413)
    return data


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
    language_code = selected_language(settings, language)

    try:
        data = await read_upload(file, settings)
        return await request.app.state.ocr_service.process(
            data,
            file.content_type,
            language_code,
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


@router.post("/v1/ocr/schema", response_model=dict[str, Any])
async def ocr_schema(
    request: Request,
    file: Annotated[UploadFile, File()],
    requested_schema: Annotated[str, Form(alias="schema")],
    language: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    settings = get_settings()
    language_code = selected_language(settings, language)

    try:
        if not settings.enable_llm or not request.app.state.llm_service.ready:
            raise LLMUnavailableError
        json_schema = parse_json_schema(requested_schema)
        data = await read_upload(file, settings)
        ocr_response = await request.app.state.ocr_service.process(
            data,
            file.content_type,
            language_code,
            False,
            False,
            False,
        )
        return await request.app.state.llm_service.extract(
            ocr_response.text, json_schema
        )
    except OCRInputError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except OCRBusyError as exc:
        raise HTTPException(status_code=429, detail="OCR service is busy") from exc
    except OCRUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="PaddleOCR is not available"
        ) from exc
    except LLMInputError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except LLMBusyError as exc:
        raise HTTPException(status_code=429, detail="LLM service is busy") from exc
    except LLMOutputError as exc:
        raise HTTPException(
            status_code=502, detail="LLM returned invalid data"
        ) from exc
    except LLMUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="llama.cpp is not available"
        ) from exc
    finally:
        await file.close()


@router.post("/v1/ocr/ask", response_model=OCRAnswerResponse)
async def ocr_ask(
    request: Request,
    file: Annotated[UploadFile, File()],
    question: Annotated[str, Form()],
    language: Annotated[str | None, Query()] = None,
) -> OCRAnswerResponse:
    settings = get_settings()
    language_code = selected_language(settings, language)

    try:
        if not settings.enable_llm or not request.app.state.llm_service.ready:
            raise LLMUnavailableError
        validated_question = parse_question(question)
        data = await read_upload(file, settings)
        ocr_response = await request.app.state.ocr_service.process(
            data,
            file.content_type,
            language_code,
            False,
            False,
            False,
        )
        answer = await request.app.state.llm_service.answer(
            ocr_response.text, validated_question
        )
        return OCRAnswerResponse(answer=answer)
    except OCRInputError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except OCRBusyError as exc:
        raise HTTPException(status_code=429, detail="OCR service is busy") from exc
    except OCRUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="PaddleOCR is not available"
        ) from exc
    except LLMInputError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except LLMBusyError as exc:
        raise HTTPException(status_code=429, detail="LLM service is busy") from exc
    except LLMOutputError as exc:
        raise HTTPException(
            status_code=502, detail="LLM returned invalid data"
        ) from exc
    except LLMUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="llama.cpp is not available"
        ) from exc
    finally:
        await file.close()
