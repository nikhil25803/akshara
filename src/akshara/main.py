import uvicorn
from fastapi import FastAPI

from akshara import __version__
from akshara.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Akshara",
    description="From text to understanding.",
    version=__version__,
)


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
def health() -> dict[str, str]:
    return {"status": "ok"}


def run() -> None:
    uvicorn.run(
        "akshara.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
