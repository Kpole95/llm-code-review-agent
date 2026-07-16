# Contributing to LLM Code Review Agent

Thank you for your interest in contributing. This document explains how to
get set up, what the code style expectations are, and how to submit changes.

## Getting started

1. Fork the repository and clone your fork.
2. Create a virtual environment and install dependencies:
   ```bash
   uv sync
   ```
3. Copy `.env.example` to `.env` and add your `ANTHROPIC_API_KEY`.
4. Build the RAG index:
   ```bash
   uv run python -m src.rag.build_index
   ```
5. Run the test suite to confirm everything works:
   ```bash
   uv run pytest -v
   ```

## Code style

- All Python code is linted with `ruff`. Run `uv run ruff check src tests`
  before committing.
- Use type hints throughout. Pydantic models for data contracts.
- Keep functions small and single-purpose. Follow the existing module structure.
- Write docstrings for public functions and classes.

## Running tests

```bash
uv run pytest -v
```

Some tests call the live Anthropic API and require `ANTHROPIC_API_KEY` to be
set. Transient network failures are not bugs — retry if a test fails on a
connection error.

## Submitting a pull request

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Make your changes, add tests if relevant, and ensure `ruff` and `pytest`
   both pass.
3. Open a pull request against `main` with a clear description of what you
   changed and why.
4. Link any relevant issues in the PR description.

## Reporting bugs

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md) to open
an issue. Include reproduction steps, the expected behavior, and what you
actually saw.

## Suggesting features

Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md)
to open an issue. Explain the use case and why the feature would be valuable.
