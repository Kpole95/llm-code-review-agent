# Architecture — LLM Code Review Agent

This document describes the system design of the LLM Code Review Agent: what each
component does, how data flows through the pipeline, why the key decisions were
made, and how the architecture evolved from the first prototype to its current
state. It is meant to be read top to bottom by someone who has never seen the
project before.

---

## 1. What the system does

The LLM Code Review Agent takes source code — either pasted directly, loaded from
a local path, or pulled from a public GitHub pull request — and produces a list of
**findings**. Each finding describes a single bug or security vulnerability and
carries:

- the file and 1-indexed line number where it occurs,
- a severity (`low`, `medium`, `high`, `critical`),
- a category from a fixed vocabulary (e.g. `sql_injection`, `hardcoded_secret`),
- a one-sentence description,
- the exact original code snippet,
- a suggested fix (corrected code),
- a plain-English explanation of why it matters and why the fix works.

It supports **five languages**: Python, JavaScript, TypeScript, Java, and Go.

The findings are grounded in a retrieval-augmented knowledge base of secure-coding
guidance (OWASP Top 10, language best-practice notes, style guides), so the model's
judgments are anchored to reference material rather than produced purely from its
own priors.

The system is exposed three ways — a CLI, a FastAPI HTTP service, and a Streamlit
web UI — all of which call the same core pipeline. It is containerized with Docker,
has a CI pipeline (lint + tests) and a CD pipeline (build + deploy to AWS ECS) on
GitHub Actions, and records evaluation runs to MLflow with traces in LangSmith.

---

## 2. High-level data flow

```
                       ┌──────────────────────────────────────────────┐
   input source        │                 ENTRY POINTS                 │
   ───────────         │   CLI  │  FastAPI /review  │  Streamlit UI   │
   paste / path / PR   └───────────────────┬──────────────────────────┘
                                           │  list[FileInput]
                                           ▼
                            ┌──────────────────────────────┐
                            │      run_review(files)        │
                            │   (compiled LangGraph graph)  │
                            └──────────────┬────────────────┘
                                           │
        ┌──────────────────────────────────────────────────────────────┐
        │                        LANGGRAPH PIPELINE                      │
        │                                                                │
        │   analyze ───────────▶ detect ───────────▶ enrich ───▶ END    │
        │      │                    │                    │               │
        │  parse structure     bug_detector        for each finding:     │
        │  (tree-sitter,       + security_scanner   - RAG context        │
        │   informational)     then deduplicate     - suggested fix      │
        │                                            - explanation        │
        │                                            - scrub UI leakage   │
        └──────────────────────────────────────────────────────────────┘
                                           │  list[dict] findings
                                           ▼
                            ┌──────────────────────────────┐
                            │   returned to entry point     │
                            │  (rendered / serialized)      │
                            └──────────────────────────────┘

   SUPPORTING SUBSYSTEMS
   ─────────────────────
   knowledge_base/*.md ──build_index──▶ ChromaDB vector store ──▶ retriever
   eval harness (test_set, holdout) ──▶ metrics ──▶ MLflow
   llm_client ──▶ Anthropic Messages API (wrapped by LangSmith)
```

The single most important architectural property is that **every entry point calls
exactly one function — `run_review(files)`** — and that function runs a single
compiled LangGraph graph. There is no duplicated review logic across the CLI, the
API, and the UI. This is what keeps the three interfaces consistent.

---

## 3. The data contract: `FileInput` and `BugFinding`

Everything in the system is built around two shapes, both defined in
`src/agent/state.py`.

**`FileInput`** is the input unit — a `TypedDict` with `path`, `content`, and
`language`. Whatever the entry point (paste, directory walk, GitHub PR), the input
is always normalized into a `list[FileInput]` before it touches the pipeline.

**`BugFinding`** is a Pydantic model and the output unit. It is filled in
incrementally as it moves through the pipeline:

- `detect` populates `file`, `line`, `severity`, `category`, `description`,
  `original_snippet`, and (for security findings) `context_docs`.
- `enrich` fills `context_docs` if empty, then `suggested_fix`, then `explanation`.

Using one Pydantic model end to end means validation happens automatically and the
fields are guaranteed to have the right types before they reach the UI.

**`AgentState`** is the third shape — the `TypedDict` that LangGraph threads through
the pipeline. It carries `files` (the input) and `findings` (the growing list of
results as plain dicts). Findings are stored as dicts inside the state and
re-hydrated into `BugFinding` objects at each node; this keeps the state JSON-
serializable, which LangGraph prefers.

---

## 4. The LangGraph pipeline

The pipeline is defined in `src/agent/graph.py` as a three-node directed graph:
`analyze → detect → enrich → END`. It is compiled once at import time
(`_compiled_graph = build_graph()`) so the graph structure is built a single time
per process, not per request.

### 4.1 `analyze_node`

Parses each file's structure using tree-sitter (via `code_parser.parse_file`) and
prints a short summary (function count, lines of code). This node is
**informational only** — it does not gate detection. If a file is in an
unsupported language, it is logged and skipped here, but detection still runs.

The reason this node exists is partly diagnostic (it surfaces parse problems early)
and partly architectural honesty: the structural parse is available for future
features (e.g. function-level scoping of findings) without being on the critical
path today.

### 4.2 `detect_node`

The heart of detection. For every file it runs **two independent detectors** and
concatenates their findings:

1. **`bug_detector.detect_bugs`** — general bugs and logic errors.
2. **`security_scanner.scan_security`** — security vulnerabilities, combining a
   deterministic regex pass with an OWASP-grounded LLM pass.

It then runs **`deduplicate_findings`** on the combined list before writing it to
state. Deduplication is essential because the two detectors overlap by design — a
hardcoded secret, for example, is caught by both the regex scanner and the LLM bug
detector. Without dedup the same issue would appear as multiple findings.

### 4.3 `enrich_node`

For each finding, in order:

1. Attaches RAG context (`get_context_for_finding`) if not already present.
2. Generates a suggested fix (`suggest_fix`) if there is an original snippet.
3. Generates a plain-English explanation (`explain_finding`).
4. Scrubs any leaked UI-template HTML from the text fields.

Enrichment is the most expensive node because steps 2 and 3 are each an LLM call
per finding. This node was **parallelized** (see §10.4) so that a file with many
findings does not block for a minute on sequential calls.

---

## 5. The two-detector design

A recurring question is *why two detectors instead of one?* The answer is
**defense in depth and precision**.

- **`bug_detector`** is a single forced-tool-use LLM call that returns findings
  conforming to a JSON schema. It is general-purpose and catches the broad class
  of logic bugs (bare excepts, resource leaks, mutable defaults, race conditions,
  integer overflow, etc.).

- **`security_scanner`** has two halves:
  - A **regex pass** (`_regex_findings`) that deterministically catches the two
    highest-confidence, highest-cost classes: hardcoded secrets/credentials and
    `eval`/`exec` usage. These are zero-cost (no API call) and never miss the
    obvious cases, which gives the system a reliable floor.
  - An **LLM pass** (`_llm_findings`) that retrieves OWASP context from the
    knowledge base and does a security-focused review grounded in that context.
    It is told explicitly which patterns are *safe* (e.g. `textContent`,
    `os.getenv`, parameterized queries) to suppress common false positives.

The regex pass guarantees recall on the scariest issues; the LLM passes provide
breadth; the knowledge base keeps the security pass grounded; and deduplication
reconciles their overlap. This layered structure is the reason recall on the
hold-out set is consistently high (≈0.90).

---

## 6. The LLM client layer

All model access goes through `src/agent/llm_client.py`, which wraps the Anthropic
Messages API and exposes three functions:

- **`chat`** — a single user-message request returning text. Used by the fix
  suggester and explainer.
- **`chat_json`** — like `chat` but parses the reply as JSON, with a one-shot
  self-repair retry if the first parse fails (it asks the model to fix its own
  malformed JSON).
- **`chat_tool`** — a *forced tool call*. This is the key to reliable structured
  output: the request sets `tool_choice` to force a specific tool, so the model
  must return arguments matching the tool's `input_schema`. This is how both
  detectors guarantee that findings always have valid `severity` and `category`
  values from the allowed enums.

The client is wrapped with `wrap_anthropic` from LangSmith so every call is traced
automatically, with tags and metadata (file, language, severity) attached for
filtering in the LangSmith UI.

The API key is validated **here**, at client-construction time — not globally at
config import. This placement is the result of a CI bug fix (see §10.1).

---

## 7. Parsing and input loaders

`src/parsing/` contains the three ways code enters the system:

- **`code_parser.py`** — wraps tree-sitter for all five languages. It maps each
  language to its tree-sitter grammar and to the set of AST node types that count
  as functions and imports (each language names these differently — e.g. Python's
  `function_definition` vs Java's `method_declaration`). It returns a `ParsedFile`
  with function list, import list, and line count.

- **`pr_loader.py`** — the single source of truth for the
  **extension→language map (`EXT_LANG`)**. `load_path` handles either a single
  file or a directory (walking it recursively), returning `list[FileInput]`. The
  UI's language dropdown is also derived from `EXT_LANG`, so the supported-language
  list can never drift between the loader and the UI.

- **`github_loader.py`** — fetches changed files from a public GitHub PR via the
  REST API. It parses the PR URL, calls the `/pulls/{n}/files` endpoint, filters to
  supported extensions, and downloads each file's raw content. It sends a
  `User-Agent` header (GitHub rejects API requests without one) and optionally an
  `Authorization: Bearer` header if a `GITHUB_ACCESS_TOKEN` is set, which raises
  the rate limit from 60/hour (unauthenticated) to 5,000/hour.

---

## 8. The RAG knowledge base

The retrieval-augmented generation subsystem grounds security findings in
reference material.

- **`knowledge_base/*.md`** — the source documents: `owasp_top10.md`,
  `python_best_practices.md`, `javascript_best_practices.md`, `style_guides.md`.
  These are **functional input data, not documentation** — the system cannot build
  its index without them, so they are committed to the repo.

- **`rag/build_index.py`** — chunks the markdown (500-char chunks, 50-char overlap,
  via LangChain's `RecursiveCharacterTextSplitter`), embeds each chunk with the
  `all-MiniLM-L6-v2` sentence-transformer, and writes them to a persistent ChromaDB
  collection named `code_review_kb`. It is run once at Docker build time so the
  container ships with the index already built and needs no external volume.

- **`rag/retriever.py`** — queries the persisted collection and returns the top-k
  most similar chunks for a query string.

- **`tools/rag_tool.py`** — builds the retrieval query from a finding
  (`category + description`) and fetches context for it during enrichment.

The same embedding model (`all-MiniLM-L6-v2`) is used for both RAG retrieval and
for semantic deduplication, so the model is loaded once and reused.

---

## 9. The enrichment tools

`src/tools/` holds the per-finding enrichment steps:

- **`bug_detector.py`** / **`security_scanner.py`** — the detectors (described in
  §5).
- **`rag_tool.py`** — retrieves knowledge-base context for a finding.
- **`fix_suggester.py`** — asks the model for a minimal corrected snippet to
  replace the original. It strips markdown fences and is explicitly instructed not
  to entity-escape valid HTML unless escaping *is* the security fix (this prevents
  it from mangling XSS fix code).
- **`explainer.py`** — produces a concise 2–3 sentence explanation in a collegial,
  senior-engineer tone, using the finding plus its RAG context.

---

## 10. How the architecture evolved

The current design is the result of several deliberate refactors. Recording them
here explains *why* the code looks the way it does.

### 10.1 Config validation moved out of import time

Originally `config.py` raised a `RuntimeError` at import if `ANTHROPIC_API_KEY`
was missing. This was fine locally but broke CI: the Docker build step runs
`build_index`, which imports `config`, which raised — even though building the RAG
index never needs the Claude API. **Fix:** the key check was removed from
`config.py` and moved into `llm_client.py`, right before the client is created. Now
the key is only required when the system actually intends to call the model.

### 10.2 Structured output via forced tool use

Early versions parsed findings out of free-text or loose JSON, which was brittle.
The detectors were rewritten to use **forced tool calls** (`chat_tool`), so the
model's output is schema-validated by the API. `severity` and `category` became
enums, eliminating an entire class of "model invented a category" errors.

### 10.3 Expansion to five languages

The system began Python-only, then added JavaScript, and finally TypeScript, Java,
and Go. This was driven entirely through `code_parser` (adding grammars and node-
type maps) and `pr_loader.EXT_LANG`. A latent bug surfaced here: the Streamlit
language dropdown had been **hardcoded** to `["python", "javascript"]` and never
updated. It was fixed by deriving the dropdown from `EXT_LANG` so it can never
drift again.

### 10.4 Parallelized enrichment

`enrich_node` originally ran a sequential `for` loop, so a file with N findings
made 2N sequential LLM calls and could hang for a minute. It was rewritten to use
a `ThreadPoolExecutor` (capped at 5 workers) that enriches findings concurrently.
Order is preserved via `executor.map`, and the worker cap keeps concurrent API
calls within rate limits. Within a single finding the steps remain sequential
(context → fix → explanation) because the explanation depends on the fix.

### 10.5 Two-pass deduplication with composite embeddings

Deduplication grew in two stages. The first pass is an **exact match** on
`(file, line, category)`. The second is a **semantic pass**: it embeds each
finding and merges near-duplicates within a line tolerance above a cosine-
similarity threshold, keeping the higher-severity one.

The semantic pass originally embedded the `description` alone, which let
duplicates slip through when the two detectors described the same issue
differently (e.g. the LLM's "AWS secret key is hardcoded…" vs the regex's generic
"Line matches a pattern for a hardcoded credential…"). It was changed to embed a
**composite `category + description`** string, so the shared category anchors
same-type findings together and pushes genuine duplicates over the threshold. The
embedding is computed **once** outside the comparison loops to avoid latency
spikes.

### 10.6 UI-leak scrubbing middleware

The model would occasionally bleed the Streamlit card template into a snippet
field (e.g. `</div><div class="code-label">SUGGESTED FIX</div>…`). A naive
"strip all HTML tags" filter was rejected because it would destroy legitimate code
(`List<String>`, arrow functions) and the real `<h1>`/`<img>` tags inside XSS
snippets. Instead, a **targeted scrubber** cuts the text at the known leaked
template boundary and removes only div/span tags carrying the app's own CSS class
names — leaving legitimate angle-bracket code untouched. This runs as a final step
in enrichment, acting as a safety net behind the prompt-level constraints.

### 10.7 Honest evaluation: separating tuning and hold-out sets

The evaluation harness was split into a **tuning set** (`test_set/`, used while
iterating on prompts) and a **hold-out set** (`holdout/`, never seen during
development). The hold-out F1 is the number reported publicly, because the tuning-
set number is optimistically biased by the very iteration it guided. This is the
single most important methodological decision in the project.

---

## 11. Interfaces

All three interfaces are thin shells over `run_review`.

- **CLI (`src/cli.py`)** — `uv run python -m src.cli review <path>`. Loads a file
  or directory via `load_path`, runs the review, and prints findings grouped by
  file with severity-colored output using `rich`.

- **API (`src/api/main.py`)** — FastAPI app with `GET /health` and
  `POST /review`. The request/response models mirror `BugFinding` but are kept as
  separate Pydantic classes so the public HTTP contract stays stable even if
  internal pipeline fields change.

- **Web UI (`streamlit_app/app.py`)** — a Streamlit app with two modes (paste
  code, GitHub PR). It calls the API over HTTP rather than importing `run_review`
  directly, which keeps the UI and the model logic in separate containers. The
  language dropdown is derived from `EXT_LANG`. All user-supplied content is
  HTML-escaped before being placed in the custom finding cards, and missing
  snippets fall back to a placeholder string rather than rendering an empty box.

---

## 12. Deployment and operations

- **Docker** — `docker/Dockerfile` builds a single image: installs dependencies
  with `uv`, copies the source, builds the RAG index at image-build time, and runs
  the FastAPI service with uvicorn. `docker-compose.yml` brings up the API and the
  Streamlit UI together, with the UI pointed at the API over the compose network.

- **CI (`.github/workflows/ci.yml`)** — on every push/PR: installs deps, runs
  `ruff` lint on `src` and `tests`, builds the RAG index, and runs `pytest`.

- **CD (`.github/workflows/deploy.yml`)** — on push to `main`: configures AWS
  credentials, logs into ECR, builds and pushes the image (tagged with the commit
  SHA and `latest`), and forces a new ECS deployment.

- **AWS** — the image runs on ECS (cluster `llm-code-review-agent-cluster`,
  service `llm-code-review-agent-task-service-cbiquzrj`) pulling from ECR in
  region `ap-south-2`. Deployments use a dedicated, scope-limited IAM user
  (`github-actions-deploy`) whose keys live in GitHub Actions secrets, separate
  from any personal credentials. The service is scaled to zero desired tasks when
  idle to avoid cost, and scaled to one only for live demos.

- **Observability** — every model call is traced in LangSmith (via the wrapped
  client); evaluation runs are logged to MLflow (hosted on DagsHub) with
  parameters (prompt version, model, RAG k) and metrics (precision, recall, F1)
  for a queryable experiment history.

---

## 13. Design principles, summarized

1. **One pipeline, many front doors.** Every interface calls `run_review`; no
   review logic is duplicated.
2. **One data contract.** `FileInput` in, `BugFinding` out, validated by Pydantic
   end to end.
3. **Schema-forced model output.** Forced tool use makes the model's structure
   reliable instead of hoping free text parses.
4. **Layered detection.** Deterministic regex for the high-confidence cases, LLM
   for breadth, RAG for grounding, deduplication to reconcile overlap.
5. **Defensive middleware.** Prompt constraints are backed by code-level safety
   nets (HTML scrubbing, snippet fallbacks, JSON-repair retry) because models are
   probabilistic.
6. **Honest measurement.** A hold-out set the system never trained or tuned on is
   the only number reported publicly.
7. **Single sources of truth.** `EXT_LANG` defines supported languages once;
   `VALID_CATEGORIES` defines the category vocabulary once; the embedding model is
   loaded once and shared.
