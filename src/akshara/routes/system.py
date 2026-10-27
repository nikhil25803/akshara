from fastapi import APIRouter, Request, Response, status

from akshara import __version__
from akshara.config import get_settings

router = APIRouter()


@router.get("/")
def root() -> dict:
    return {
        "name": "Akshara",
        "name_native": "अक्षर",
        "version": __version__,
        "tagline": "From text to understanding.",
        "features": {
            "ocr": True,
            "llm": get_settings().enable_llm,
        },
    }


@router.get("/health", status_code=status.HTTP_200_OK)
def health(request: Request, response: Response) -> dict[str, str | bool]:
    ready = request.app.state.ocr_service.ready
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if ready else "degraded", "paddleocr": ready}
