# Contributing to LLM Code Review Agent

Thank you for your interest in contributing. This document covers everything
you need to get set up, understand the codebase, follow the code style, run
tests, and submit changes. Please read it before opening a pull request.

---

## Table of contents

- [Getting started](#getting-started)
- [Project structure](#project-structure)
- [Development workflow](#development-workflow)
- [Code style](#code-style)
- [Running tests](#running-tests)
- [Adding a new language](#adding-a-new-language)
- [Adding a new vulnerability category](#adding-a-new-vulnerability-category)
- [Submitting a pull request](#submitting-a-pull-request)
- [Reporting bugs](#reporting-bugs)
- [Suggesting features](#suggesting-features)
- [Code of conduct](#code-of-conduct)

---

## Getting started

**Prerequisites:** Python 3.11+, [uv](https://github.com/astral-sh/uv),
and an Anthropic API key.

```bash
# 1. Fork the repository and clone your fork
git clone https://github.com/YOUR_USERNAME/llm-code-review-agent.git
cd llm-code-review-agent

# 2. Install all dependencies
uv sync

# 3. Copy the environment template and add your API key
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...

# 4. Build the RAG index (required before running anything)
uv run python -m src.rag.build_index

# 5. Run the test suite to confirm everything works
uv run pytest -v
```

If all tests pass, your environment is ready.

---

## Project structure

```
src/
├── agent/          # LangGraph pipeline, state contract, prompts, LLM client
│   ├── graph.py    # run_review() entry point and the three pipeline nodes
│   ├── state.py    # FileInput, BugFinding, AgentState data contracts
│   ├── prompts.py  # VALID_CATEGORIES, system prompts, user templates
│   └── llm_client.py  # chat(), chat_json(), chat_tool() — all model calls go here
├── parsing/
│   ├── code_parser.py   # tree-sitter AST parsing for all five languages
│   ├── pr_loader.py     # EXT_LANG map, load_path(), load_directory()
│   └── github_loader.py # GitHub PR URL → list[FileInput]
├── rag/
│   ├── build_index.py   # chunks, embeds, and writes knowledge_base/ to ChromaDB
│   └── retriever.py     # retrieve_context() — queries the persisted collection
├── tools/
│   ├── bug_detector.py      # general bug detection via forced tool-use
│   ├── security_scanner.py  # regex pass + RAG-grounded LLM security scan
│   ├── fix_suggester.py     # generates a corrected code snippet per finding
│   ├── explainer.py         # generates a plain-English explanation per finding
│   └── rag_tool.py          # get_context_for_finding() bridge
├── eval/
│   ├── metrics.py       # match_findings(), MatchResult, precision/recall/F1
│   ├── run_eval.py      # evaluation against the tuning set
│   ├── run_holdout.py   # honest evaluation against the held-out set
│   ├── mlflow_logger.py # logs a run's params and metrics to MLflow/DagsHub
│   ├── test_set/        # labeled snippets used during prompt iteration
│   └── holdout/         # held-out snippets never used during development
├── api/
│   └── main.py      # FastAPI service: GET /health, POST /review
└── cli.py           # command-line interface: uv run python -m src.cli review <path>

streamlit_app/
└── app.py           # Streamlit web UI (calls the API over HTTP)

knowledge_base/      # OWASP and language best-practice markdown docs (required)
docker/
└── Dockerfile       # single image for both API and Streamlit containers
.github/
├── workflows/
│   ├── ci.yml       # lint + test on every push and pull request
│   └── deploy.yml   # build → ECR → ECS on push to main
└── ISSUE_TEMPLATE/  # bug report and feature request templates
```

The single most important design rule: **every entry point calls
`run_review(files)` and nothing else.** The CLI, the API, and the Streamlit
UI are all thin shells. All review logic lives in `src/agent/graph.py`.

---

## Development workflow

```bash
# Run the CLI on a single file
uv run python -m src.cli review tests/fixtures/sql_injection.py

# Run the CLI on a directory
uv run python -m src.cli review src/

# Start the full stack (API + UI)
docker compose up --build

# Run only the API (no Docker)
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

# Run only the Streamlit UI (no Docker, API must already be running)
uv run streamlit run streamlit_app/app.py

# Re-build the RAG index after editing knowledge_base/ files
uv run python -m src.rag.build_index

# Run the tuning-set evaluation (optimistically biased — for iteration only)
uv run python -m src.eval.run_eval

# Run the held-out evaluation (the honest number to report)
uv run python -m src.eval.run_holdout

# Log a run to MLflow / DagsHub
uv run python -m src.eval.mlflow_logger
```

---

## Code style

All Python code is linted with **ruff**. Run this before committing:

```bash
uv run ruff check src tests
```

Key conventions used throughout the codebase:

- **Type hints everywhere.** Use `TypedDict` for plain dicts passed between
  layers, `Pydantic BaseModel` for data that needs validation.
- **Pydantic for contracts.** `FileInput` (input), `BugFinding` (output), and
  the API request/response models are all Pydantic-typed. If you add a field,
  add the type annotation.
- **No bare `except:`.** Catch specific exception types. If you need a catch-all
  in a route handler, log the exception before re-raising — otherwise production
  debugging goes blind.
- **One source of truth.** `VALID_CATEGORIES` in `prompts.py` is the only place
  category names are defined. `EXT_LANG` in `pr_loader.py` is the only place
  supported languages and file extensions are defined. Do not duplicate them.
- **Single entry point.** All review logic flows through `run_review()` in
  `graph.py`. Do not add review logic in the CLI, API, or UI.
- **Mutable default safety.** Never use `= []` or `= {}` as a default argument
  or class field. Always use `default_factory`.
- **Keep functions small.** Each function should have one responsibility. If a
  function is doing two things, split it.
- **Structured logging over print.** Use `print()` only for user-facing CLI
  output (`[analyze] file.py: 3 functions`). Use proper logging for anything
  diagnostic.

---

## Running tests

```bash
# Run all tests with verbose output
uv run pytest -v

# Run a specific test file
uv run pytest tests/test_bug_detector.py -v

# Run tests matching a keyword
uv run pytest -k "sql" -v
```

Some tests call the live Anthropic API and require `ANTHROPIC_API_KEY` to be
set in `.env`. Transient `APITimeoutError` or `getaddrinfo failed` failures
are network blips, not bugs — retry if a live-API test fails once.

The `src/eval/test_set/snippets/` and `src/eval/holdout/snippets/` directories
contain deliberately vulnerable code as test fixtures. They are excluded from
ruff linting in `pyproject.toml` — do not remove those exclusions.

When adding new features, please add a corresponding test in `tests/`. If your
change touches the evaluation pipeline, run both `run_eval` and `run_holdout`
and confirm F1 does not regress.

---

## Adding a new language

1. Install the tree-sitter grammar:
   ```bash
   uv add tree-sitter-<language>
   ```
2. Import and register it in `src/parsing/code_parser.py`:
   - Add the `Language(ts<lang>.language())` constant
   - Add entries to `_PARSERS`, `_FUNCTION_NODE_TYPES`, and `_IMPORT_NODE_TYPES`
3. Add the file extension mapping in `src/parsing/pr_loader.py`:
   ```python
   EXT_LANG[".ext"] = "language_name"
   ```
   The Streamlit UI language dropdown is derived from `EXT_LANG` automatically —
   you do not need to update it separately.
4. Add at least one test fixture in `tests/fixtures/` and a labeled snippet
   in `src/eval/test_set/snippets/` with a corresponding entry in
   `src/eval/test_set/manifest.json`.
5. Run `uv run pytest -v` and confirm the new fixture is exercised.

---

## Adding a new vulnerability category

1. Add the category string to `VALID_CATEGORIES` in `src/agent/prompts.py`.
   Use `snake_case` and keep it concise (e.g. `prototype_pollution`,
   `integer_overflow`).
2. The category is immediately available in both detectors' tool schemas and
   in the evaluation harness — no other changes needed.
3. Optionally add relevant OWASP or best-practice content to one of the
   `knowledge_base/*.md` files and rebuild the RAG index:
   ```bash
   uv run python -m src.rag.build_index
   ```
4. Add a labeled holdout or test-set snippet that demonstrates the new
   category so it is covered by evaluation.

---

## Submitting a pull request

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Make your changes. If you are fixing a bug, add a test that reproduces it
   first, then fix it.
3. Confirm both checks pass:
   ```bash
   uv run ruff check src tests
   uv run pytest -v
   ```
4. Push your branch and open a pull request against `main`.
5. In the PR description:
   - Explain what the change does and why
   - Link any related issues (`Closes #123`)
   - Note if you changed prompts and what the eval impact was

PR reviews focus on correctness, test coverage, and consistency with the
existing architecture. Keep PRs focused — one feature or fix per PR makes
review faster and merging easier.

---

## Reporting bugs

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md). Include:
- Exact steps to reproduce
- What you expected to happen
- What actually happened (include full error messages and tracebacks)
- Your environment (OS, Python version, uv version)
- Whether you are running via Docker or directly with uv

---

## Suggesting features

Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md).
Explain the use case and why the feature would be valuable before describing
the implementation — understanding the problem first helps the discussion.

---

## Code of conduct

This project follows the
[Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
Be respectful and constructive in all interactions. Harassment of any kind
will not be tolerated. If you experience or witness unacceptable behavior,
please report it to krishnapole90@outlook.com.