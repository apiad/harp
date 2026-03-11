.PHONY: all test lint format check

all: check

test:
	@echo "Running unit tests..."
	uv run pytest -m "not integration" --cov=src --cov-report=term-missing

test-integration:
	@echo "Running integration tests..."
	uv run pytest -m "integration" -s

lint:
	@echo "Running linter..."
	uv run ruff check .
	uv run ruff format --check .

format:
	@echo "Formatting code..."
	uv run ruff format .

check: format lint test
