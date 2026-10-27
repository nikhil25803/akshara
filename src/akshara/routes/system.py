from fastapi import APIRouter, Request

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


@router.get("/health")
def health(request: Request) -> dict[str, str | bool]:
    ready = request.app.state.ocr_service.ready
    return {"status": "ok" if ready else "degraded", "paddleocr": ready}
