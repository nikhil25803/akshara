FROM ghcr.io/astral-sh/uv:0.9.18 AS uv

FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    UV_HTTP_TIMEOUT=600

COPY --from=uv /uv /bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
# Base dependencies install PaddleOCR; the ocr extra adds Linux PaddlePaddle.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project --extra ocr \
    && rm -rf /app/.venv/lib/python3.11/site-packages/paddle/include

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --extra ocr

FROM python:3.11-slim AS runtime

ENV ENABLE_LLM=false \
    PADDLE_PDX_CACHE_HOME=/models \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && useradd --create-home --uid 10001 app \
    && mkdir /models \
    && chown app:app /models \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv

USER app

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "akshara.main:app", "--host", "0.0.0.0", "--port", "8000"]
