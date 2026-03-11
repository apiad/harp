# Development Guide

This guide is for developers who want to contribute to Harp or run it from source.

## 🛠 Prerequisites

Harp uses **`uv`** for dependency management. Ensure it is installed on your system.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 🚀 Setting Up the Project

```bash
# Clone and install dependencies
git clone https://github.com/apiad/harp.git
cd harp
uv sync
```

## 🧪 Testing Strategy

Harp has a comprehensive test suite consisting of unit and integration tests.

### Unit Tests
Unit tests use mocks for AI models and audio hardware, ensuring they can run in any CI environment.
```bash
# Run unit tests
make test
```

### Integration Tests
Integration tests use real Whisper models and ground truth audio assets (`tests/assets/`) to verify accuracy. These are skipped by default.
```bash
# Run integration tests (requires 'base' model downloaded)
make test-integration
```

## 🖋 Code Style & Standards

We use **`ruff`** for linting and formatting.

- **Check Linter**: `make lint`
- **Apply Formatting**: `uv run ruff format .`

## 🛠 Helpful Commands

The `makefile` provides a convenient interface for common development tasks:

- `make build`: Install dependencies.
- `make test`: Run unit tests with coverage report.
- `make lint`: Run all code quality checks.
- `make clean`: Remove caches and build artifacts.

---

*Next: See [Internal Architecture](design.md) to understand the code structure.*
