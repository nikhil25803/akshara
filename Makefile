.DEFAULT_GOAL := help

IMAGE ?= akshara
TAG ?= local

.PHONY: help sync run lint format test check docker-build docker-run

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z_-]+:.*## / {printf "%-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync: ## Install locked development dependencies
	uv sync --locked

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
	docker build --tag $(IMAGE):$(TAG) .

docker-run: ## Run the local Docker image
	docker run --rm --publish 8000:8000 --env ENABLE_LLM=false $(IMAGE):$(TAG)
