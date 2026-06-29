.PHONY: all test lint format check

all: check

# --extra cli: the engine is the published base package; harp's own daemon/CLI
# tests need the cli extra, so the dev/test env always installs it.
test:
	@echo "Running unit tests..."
	uv run --extra cli pytest -m "not integration" --cov=src --cov-report=term-missing

test-integration:
	@echo "Running integration tests..."
	uv run --extra cli pytest -m "integration" -s

lint:
	@echo "Running linter..."
	uv run --extra cli ruff check .
	uv run --extra cli ruff format --check .

format:
	@echo "Formatting code..."
	uv run --extra cli ruff format .

check: format lint test
