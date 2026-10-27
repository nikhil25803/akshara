.DEFAULT_GOAL := help

IMAGE ?= akshara
TAG ?= local
DOCKER_PLATFORM ?= linux/amd64
PYTHON ?= python3

.PHONY: help sync sync-ocr generate-key run lint format test check docker-build docker-run

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z_-]+:.*## / {printf "%-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync: ## Install locked development dependencies
	uv sync --locked

sync-ocr: ## Install the Linux PaddlePaddle runtime
	uv sync --locked --extra ocr

generate-key: ## Generate a strong local API key with Python
	@$(PYTHON) -c 'import secrets; print("Generated API_KEY (save it securely; shown once):\n" + secrets.token_urlsafe(32))'

run: ## Run the development server
	uv run uvicorn akshara.main:app --host 127.0.0.1 --port 8000 --reload

lint: ## Check code with Ruff
	uv run ruff check .

format: ## Format code with Ruff
	uv run ruff format .

test: ## Run the test suite
	uv run pytest

check: lint test ## Run all CI checks
	uv run ruff format --check .

docker-build: ## Build the local Docker image
	docker build --platform $(DOCKER_PLATFORM) --tag $(IMAGE):$(TAG) .

docker-run: ## Run the local Docker image
	docker run --rm --platform $(DOCKER_PLATFORM) --publish 8000:8000 --env-file .env --volume akshara-models:/models $(IMAGE):$(TAG)
