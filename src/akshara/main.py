from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from akshara import __version__
from akshara.config import get_settings
from akshara.helpers.extraction import LLMService
from akshara.helpers.ocr import OCRService
from akshara.helpers.security import ApiKeyMiddleware, RequestSizeLimitMiddleware
from akshara.routes.extract import router as extract_router
from akshara.routes.ocr import router as ocr_router
from akshara.routes.system import router as system_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(app.state.ocr_service.probe)
    await run_in_threadpool(app.state.llm_service.probe)
    yield


# Initialize FastAPI app
app = FastAPI(
    title="Akshara",
    description="From text to understanding.",
    version=__version__,
    lifespan=lifespan,
)

# Initialize OCR service
app.state.ocr_service = OCRService(settings)
app.state.llm_service = LLMService(settings)

# Middlewares
app.add_middleware(
    RequestSizeLimitMiddleware,
    max_bytes=settings.max_file_size_mb * 1024 * 1024 + 64 * 1024,
)
app.add_middleware(ApiKeyMiddleware, api_key=settings.api_key.get_secret_value())

# Routers
app.include_router(system_router)
app.include_router(ocr_router)
app.include_router(extract_router)


# Run the application
def run() -> None:
    uvicorn.run(
        "akshara.main:app",
        host=settings.hostname if settings.hostname else "0.0.0.0",
        port=settings.port if settings.port else 8080,
        reload=True,
    )
