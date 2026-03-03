.PHONY: all test lint format check

all: check

test:
	@echo "Running tests..."
	uv run pytest --cov=src --cov-report=term-missing

lint:
	@echo "Running linter..."
	uv run ruff check .
	uv run ruff format --check .

format:
	@echo "Formatting code..."
	uv run ruff format .

check: lint test
