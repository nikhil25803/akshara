FROM ghcr.io/astral-sh/uv:0.9.18 AS uv

FROM python:3.11-slim

ENV ENABLE_LLM=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --locked --no-dev --no-editable \
    && useradd --create-home --uid 10001 app

USER app

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "akshara.main:app", "--host", "0.0.0.0", "--port", "8000"]
