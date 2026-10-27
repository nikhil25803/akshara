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
    paddle_ready = request.app.state.ocr_service.ready
    llm_ready = request.app.state.llm_service.ready
    ready = paddle_ready and (not get_settings().enable_llm or llm_ready)
    return {
        "status": "ok" if ready else "degraded",
        "paddleocr": paddle_ready,
        "llama_cpp": llm_ready,
    }
