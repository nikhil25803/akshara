from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

from akshara.config import get_settings
from akshara.helpers.extraction import (
    ExtractionInputError,
    ExtractionResponse,
    LLMBusyError,
    LLMOutputError,
    LLMUnavailableError,
    parse_template,
)
from akshara.helpers.ocr import (
    OCRBusyError,
    OCRInputError,
    OCRUnavailableError,
    read_upload,
    select_ocr_language,
)

router = APIRouter()


@router.post(
    "/v1/extract", response_model=ExtractionResponse, response_model_exclude_none=True
)
async def extract(
    request: Request,
    file: Annotated[UploadFile, File()],
    prompt: Annotated[str, Form(min_length=1, max_length=4000)],
    template: Annotated[str | None, Form(max_length=32 * 1024)] = None,
    language: Annotated[str | None, Query()] = None,
    evidence: Annotated[bool, Query()] = False,
) -> ExtractionResponse:
    settings = get_settings()
    try:
        prompt = prompt.strip()
        if not prompt:
            raise ExtractionInputError("Prompt cannot be blank")
        parsed_template = parse_template(template)
        if not request.app.state.llm_service.available:
            raise LLMUnavailableError
        selected_language = select_ocr_language(settings, language)
        data = await read_upload(file, settings.max_file_size_mb)
        ocr_result = await request.app.state.ocr_service.process(
            data,
            file.content_type,
            selected_language,
            True,
            False,
            False,
        )
        if not ocr_result.text.strip():
            raise ExtractionInputError("No text could be extracted from the document")
        pages = [
            {"page_number": page.page_number, "text": page.text or ""}
            for page in ocr_result.pages or []
        ]
        result = await request.app.state.llm_service.extract(
            pages, prompt, parsed_template, evidence
        )
        result.warnings = list(dict.fromkeys([*ocr_result.warnings, *result.warnings]))
        return result
    except (OCRInputError, ExtractionInputError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except (OCRBusyError, LLMBusyError) as exc:
        raise HTTPException(
            status_code=429, detail="Processing service is busy"
        ) from exc
    except OCRUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="PaddleOCR is not available"
        ) from exc
    except LLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail="LLM is not available") from exc
    except LLMOutputError as exc:
        raise HTTPException(
            status_code=502, detail="LLM returned invalid output"
        ) from exc
    finally:
        await file.close()
