FROM ghcr.io/astral-sh/uv:0.9.18 AS uv

FROM python:3.11-slim

ENV ENABLE_LLM=false \
    LLM_MODEL_PATH=/models/model.gguf \
    PADDLE_PDX_CACHE_HOME=/models \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential cmake libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Project dependencies install PaddleOCR; extras add PaddlePaddle and llama.cpp.
RUN uv sync --locked --no-dev --no-editable --extra ocr --extra llm \
    && apt-get purge --auto-remove --yes build-essential cmake \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app \
    && mkdir /models \
    && chown app:app /models

USER app

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "akshara.main:app", "--host", "0.0.0.0", "--port", "8000"]
