# Scaffolding Plan: CI/CD Workflows

This plan outlines the creation of two GitHub Actions workflows for the `harp` project.

## Phase 1: CI Workflow (Commit-based)
- [ ] Create `.github/workflows/ci.yml`.
- [ ] Trigger on `push` to `main` and all `pull_request` events.
- [ ] Implement a Matrix Strategy:
    - **Python**: `3.12`, `3.13`
    - **OS**: `ubuntu-22.04`, `ubuntu-24.04` (Linux Matrix)
- [ ] Steps:
    - Checkout code.
    - Install `uv`.
    - Set up Python.
    - Install dependencies using `uv sync`.
    - Run `make check` (runs lint and tests).

## Phase 2: CD Workflow (Release-based)
- [ ] Create `.github/workflows/release.yml`.
- [ ] Trigger on `release` with type `published`.
- [ ] Steps:
    - Checkout code.
    - Install `uv`.
    - Set up Python 3.12.
    - Build the package using `uv build`.
    - Publish to PyPI using `uv publish` (requires `PYPI_TOKEN` secret).

## Phase 3: Project Integration
- [ ] Update `makefile` if needed to ensure `make check` is the standard CI entry point.
- [ ] Update `journal/2026-03-03.md` with the new automation setup.

## Technical Considerations
- **Hardware Access**: Since CI environments lack access to `/dev/input`, tests that interact with `evdev` directly might fail. We should ensure unit tests are mocked where possible or that the CI handles these failures gracefully.
- **PyPI Token**: The user must add `PYPI_TOKEN` to GitHub Repository Secrets.
