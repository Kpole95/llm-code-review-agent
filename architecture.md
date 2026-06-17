# LLM Code Review Agent — Technical Documentation

An autonomous agent that reviews source code and pull requests, detecting
bugs and security vulnerabilities, retrieving relevant best-practice
context, generating fixes, and producing human-readable explanations. Built
with LangGraph, the Anthropic API, ChromaDB-backed retrieval, a custom
evaluation harness, and full observability through LangSmith and MLflow.

This document explains the system from first principles: the problem it
solves, the architecture, every component and how they connect, the design
decisions behind them, and how the system is evaluated and deployed.

---

## 1. Problem and motivation

Code review is a high-value but time-consuming task. A competent reviewer
looking at a pull request performs a sequence of mental steps: they read
the code to understand its structure, identify suspicious patterns, recall
the relevant rule or best practice, propose a corrected version, and
explain why the change matters. Each of these is something a large language
model can assist with — but only if the surrounding system feeds it the
right information at each step and verifies its output.

The goal of this project is to automate that review process end to end: a
file or pull request goes in, and a structured set of findings comes out,
each consisting of a location, a severity, a category, a description, a
suggested fix, and an explanation grounded in established guidelines.

The system is designed to be usable three ways — from the command line, as
an HTTP API, and through a web interface that can review a live GitHub pull
request — and to be measurable, so that its accuracy is a tracked metric
rather than a subjective impression.

---

## 2. High-level architecture

The system is organized around a single core function, `run_review()`,
which accepts a list of files and returns a list of findings. Everything
else either produces input for this function or consumes its output.

The review itself is a three-stage pipeline implemented as a LangGraph
state machine:

```
 Input: list of files [{path, content, language}]
        │
        ▼
 ┌─────────────────────────────────────────────┐
 │ Stage 1 — analyze                            │
 │ Parse each file's structure (tree-sitter)    │
 └─────────────────────────────────────────────┘
        │
        ▼
 ┌─────────────────────────────────────────────┐
 │ Stage 2 — detect                             │
 │ Run two independent detectors per file:      │
 │   • general bug detector (LLM)               │
 │   • security scanner (regex + OWASP-grounded │
 │     LLM)                                      │
 │ Deduplicate overlapping findings             │
 └─────────────────────────────────────────────┘
        │
        ▼
 ┌─────────────────────────────────────────────┐
 │ Stage 3 — enrich (per finding)               │
 │   1. retrieve best-practice context (RAG)    │
 │   2. generate a suggested fix                │
 │   3. generate an explanation                 │
 └─────────────────────────────────────────────┘
        │
        ▼
 Output: fully-populated findings
```

Three input adapters all converge on the same `FileInput` shape, so the
core pipeline is agnostic to how code arrives:

```
 Command line ──┐
 HTTP API ──────┼──▶ list[FileInput] ──▶ run_review()
 GitHub PR URL ─┘
```

Two supporting subsystems sit alongside the pipeline:

- A **retrieval-augmented knowledge base**: a curated set of best-practice
  and OWASP documents, embedded into a vector store, queried at runtime to
  ground both detection and explanation.
- An **evaluation harness**: a labeled test set, a scoring module computing
  precision/recall/F1, and experiment tracking that records accuracy across
  runs and prompt versions.

---

## 3. Project structure

```
llm-code-review-agent/
├── knowledge_base/            Curated best-practice and OWASP reference docs
├── chroma_db/                 Generated vector index (gitignored)
├── src/
│   ├── config.py              Centralized settings/secrets loader
│   ├── cli.py                 Command-line entry point
│   ├── agent/
│   │   ├── state.py           Data models (FileInput, BugFinding, AgentState)
│   │   ├── prompts.py         Versioned prompt templates
│   │   ├── llm_client.py      Anthropic API wrapper with tracing + safety nets
│   │   └── graph.py           The LangGraph pipeline (run_review)
│   ├── parsing/
│   │   ├── code_parser.py     tree-sitter structural analysis
│   │   ├── pr_loader.py       Local file/directory loader
│   │   └── github_loader.py   GitHub PR loader (REST API)
│   ├── rag/
│   │   ├── build_index.py     Builds the vector index from knowledge_base/
│   │   └── retriever.py       Queries the vector index
│   ├── tools/
│   │   ├── code_analyzer.py   Structural-analysis tool
│   │   ├── bug_detector.py    General bug detection (LLM)
│   │   ├── security_scanner.py Security detection (regex + OWASP-grounded LLM)
│   │   ├── rag_tool.py        Per-finding context retrieval
│   │   ├── fix_suggester.py   Fix generation
│   │   └── explainer.py       Explanation generation
│   ├── api/
│   │   └── main.py            FastAPI service
│   └── eval/
│       ├── metrics.py         Matching logic + precision/recall/F1
│       ├── run_eval.py        Eval runner over the labeled test set
│       ├── mlflow_logger.py   Logs eval runs to MLflow/DagsHub
│       ├── check_regression.py Variance-aware regression gate
│       └── test_set/          Labeled snippets + ground-truth manifest
├── streamlit_app/
│   └── app.py                 Web interface
├── docker/Dockerfile          Container image definition
├── docker-compose.yml         Multi-service local orchestration
└── tests/                     Unit and integration tests
```

The structure follows a single principle: each module has one
responsibility. Detection logic, retrieval logic, prompt text, API
plumbing, and evaluation are all separated so that a change to one rarely
forces a change to another.

---

## 4. Configuration and secrets

`src/config.py` is the single source of truth for configuration. It loads
environment variables from a `.env` file once at import time and exposes
them as an immutable `Settings` object. Every module that needs an API key
or setting imports this object rather than reading the environment
directly, which keeps configuration access consistent and makes missing
configuration fail loudly at startup rather than deep inside a request.

```python
@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    mlflow_tracking_uri: str = os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db")
    # ...

settings = Settings()
if not settings.anthropic_api_key:
    raise RuntimeError("ANTHROPIC_API_KEY not set.")
```

Secrets live only in `.env`, which is excluded from version control. A
`.env.example` documents the required keys without exposing values.

---

## 5. Data models

`src/agent/state.py` defines the shapes that flow through the system,
established before any logic so that every component agrees on the contract.

`FileInput` describes one file to review:

```python
class FileInput(TypedDict):
    path: str
    content: str
    language: str  # "python" | "javascript"
```

`BugFinding` is the central object. It is built up incrementally — the
detector fills in location and classification, retrieval attaches context,
and later stages add the fix and explanation:

```python
class BugFinding(BaseModel):
    file: str
    line: int
    severity: str        # low | medium | high | critical
    category: str        # e.g. sql_injection
    description: str
    original_snippet: str | None = None
    suggested_fix: str | None = None
    explanation: str | None = None
    context_docs: list[str] = Field(default_factory=list)
```

Using a Pydantic model rather than a plain dictionary means the model's
output is validated against this schema. If the language model returns a
field of the wrong type or omits a required field, the error surfaces
immediately at construction time rather than corrupting data further down
the pipeline.

---

## 6. The LLM client

`src/agent/llm_client.py` is the only module that calls the Anthropic API
directly. Every tool routes its model calls through it. Centralizing this
provides three benefits: a single place to configure the model and
defaults, automatic tracing of every call, and shared output-handling logic.

The Anthropic client is wrapped with LangSmith's tracing wrapper, so every
call is recorded with its inputs, outputs, latency, and cost. Calls accept
optional `tags` and `metadata` so traces can be filtered by tool and by
finding category during debugging.

```python
_client = wrap_anthropic(anthropic.Anthropic(api_key=settings.anthropic_api_key))

def chat(prompt, system=None, max_tokens=1024, tags=None, metadata=None) -> str:
    ...

def chat_json(prompt, ...):
    """Expects a JSON response and parses it. If parsing fails — for
    example when the model emits an unescaped quote inside a string — it
    sends the malformed text back to the model with the parse error and
    asks it to correct the JSON, then parses again."""
    ...
```

Two pieces of defensive output handling proved necessary in practice.
Models do not perfectly obey "respond with only JSON" or "do not use
markdown fences." A `_strip_fences` helper removes code-fence wrappers
(including language tags such as `python` or `json`), and `chat_json`
includes a self-repair retry that asks the model to fix its own invalid
JSON. Both handle real failure modes observed during development rather
than hypothetical ones.

---

## 7. Input: parsing and loading

### Structural parsing

`src/parsing/code_parser.py` uses tree-sitter to parse source into an
abstract syntax tree and extract function definitions (with line ranges)
and imports. This is deterministic, instant, and free — unlike asking a
model "what functions are in this file," it never miscounts a line or
hallucinates. It supports Python and JavaScript through their respective
tree-sitter grammars.

### Loaders

Three loaders produce the same `FileInput` list:

- `pr_loader.py` reads a local file or directory, filtering to supported
  extensions via a shared `EXT_LANG` map.
- `github_loader.py` accepts a GitHub pull request URL, calls the GitHub
  REST API to enumerate changed files, and fetches each file's content.
- The web interface's "paste code" mode constructs the list directly.

Because all three produce identical output, the core pipeline never needs
to know where the code came from. Adding a new input source is isolated to
a new loader.

---

## 8. Retrieval-augmented knowledge base

The system grounds its security analysis and explanations in a curated
knowledge base rather than relying solely on the model's parametric
knowledge. This serves consistency (the same issue is categorized the same
way every time), customizability (an organization can swap in its own
standards), and authority (explanations can reference established guidance).

`knowledge_base/` contains markdown documents covering the OWASP Top 10,
language-specific best practices, and style guidelines, written as concise
summaries.

`rag/build_index.py` is a build step run when the knowledge base changes.
It splits each document into overlapping chunks, embeds each chunk locally
with a sentence-transformer model (no API cost), and persists them to a
ChromaDB vector store.

```python
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
embed_fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
collection = client.create_collection(COLLECTION_NAME, embedding_function=embed_fn)
collection.add(documents=chunks, ids=ids, metadatas=metadatas)
```

`rag/retriever.py` is the runtime read path. Given a query, it embeds it
with the same model and returns the most semantically similar chunks. The
build and query paths deliberately share the embedding model and collection
name — querying with a different embedding model than was used to build the
index would make similarity search meaningless.

```python
def retrieve_context(query: str, k: int = 3) -> list[str]:
    collection = client.get_collection(COLLECTION_NAME, embedding_function=embed_fn)
    results = collection.query(query_texts=[query], n_results=k)
    return results["documents"][0]
```

---

## 9. Detection

Detection uses two complementary tools, run independently on every file.
This is a deliberate defense-in-depth design: a single detector's recall
depends on how a prompt happens to be phrased, whereas two detectors with
different strategies are more reliably triggered.

### General bug detector

`tools/bug_detector.py` sends the file to the model with a system prompt
instructing it to find genuine bugs and logic errors (not style issues),
classify each by severity and a short category, and return a JSON array. It
validates each item into a `BugFinding`, skipping any malformed entry
rather than failing the whole review.

### Security scanner

`tools/security_scanner.py` combines two methods:

```python
def scan_security(code, language, file_path) -> list[BugFinding]:
    return _regex_findings(code, file_path) + _llm_findings(code, language, file_path)
```

The regex pass deterministically catches unambiguous patterns —
hardcoded credentials, `eval`/`exec` usage — at zero cost and with no risk
of hallucination. The LLM pass first retrieves OWASP context from the
knowledge base, then asks the model to identify security vulnerabilities
using that context, producing OWASP-aligned categories.

### Deduplication

Because two detectors run on the same code, the same issue can be reported
more than once, sometimes with slightly different line numbers or category
names. After detection, `deduplicate_findings()` merges findings that share
a file, fall within a small line tolerance of each other, and have similar
categories, keeping the highest-severity version. This both reduces noise
and avoids redundant downstream LLM calls during enrichment.

Notably, the function that decides "are these the same issue?" for
deduplication is the same category-matching function used by the evaluation
harness to decide "does this prediction match the expected finding?" — a
single notion of equivalence reused in two contexts.

---

## 10. Enrichment

For each deduplicated finding, the enrichment stage fills in the remaining
fields in a dependency-driven order.

1. **Context retrieval** (`tools/rag_tool.py`): builds a query from the
   finding's category and description and retrieves relevant knowledge-base
   chunks. This is skipped if the security scanner already attached context.

2. **Fix generation** (`tools/fix_suggester.py`): sends the offending
   snippet to the model and requests only the corrected code. This uses the
   plain-text path rather than the JSON path, since code contains many
   characters that complicate JSON encoding.

3. **Explanation generation** (`tools/explainer.py`): produces a concise,
   constructive explanation of why the issue matters and why the fix
   resolves it, referencing the retrieved context.

The order is mandatory: the explainer references both the retrieved context
and the suggested fix, so those must already exist. The pipeline encodes
this ordering explicitly.

---

## 11. The pipeline

`src/agent/graph.py` assembles everything into a LangGraph state machine
with three nodes — analyze, detect, enrich — connected linearly. The graph
shape is intentionally simple; the value of LangGraph here is an explicit,
inspectable execution structure and clean state passing, with room to grow
into branching or parallel fan-out.

```python
def detect_node(state):
    findings = []
    for f in state["files"]:
        findings += detect_bugs(f["content"], f["language"], f["path"])
        findings += scan_security(f["content"], f["language"], f["path"])
    state["findings"] = [x.model_dump() for x in deduplicate_findings(findings)]
    return state

def enrich_node(state):
    enriched = []
    for raw in state["findings"]:
        finding = BugFinding(**raw)
        if not finding.context_docs:
            finding.context_docs = get_context_for_finding(finding)
        if finding.original_snippet:
            finding.suggested_fix = suggest_fix(finding)
            finding.explanation = explain_finding(finding)
        enriched.append(finding.model_dump())
    state["findings"] = enriched
    return state

def run_review(files: list[dict]) -> list[dict]:
    result = _compiled_graph.invoke({"files": files, "findings": []})
    return result["findings"]
```

`run_review()` is the single entry point that every interface calls.

---

## 12. Interfaces

### Command line

`src/cli.py` exposes `review <path>` for a file or directory, rendering
findings grouped by file with color-coded severity, the original snippet,
the suggested fix, and the explanation.

### HTTP API

`src/api/main.py` is a FastAPI service exposing `GET /health` and
`POST /review`. It defines its own request and response models, decoupled
from the internal `BugFinding`, so the public API contract can remain stable
independently of internal changes. It validates input, rejects empty
requests explicitly, and converts pipeline failures into clean error
responses rather than leaking stack traces.

```python
@app.post("/review", response_model=ReviewResponse)
def review(request: ReviewRequest):
    if not request.files:
        raise HTTPException(status_code=422, detail="At least one file is required.")
    try:
        findings = run_review([f.model_dump() for f in request.files])
        return ReviewResponse(findings=findings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review failed: {e}")
```

### Web interface

`streamlit_app/app.py` provides a browser UI supporting pasted code or a
GitHub pull request URL. It deliberately calls the HTTP API rather than
`run_review()` directly — the same way any external client would. This
mirrors a real deployment, where the API is the single backend and the UI
is just one of potentially several frontends, and ensures the two cannot
silently diverge.

---

## 13. Evaluation

A review tool is only as trustworthy as its measured accuracy. The
evaluation harness turns "it seems to work" into tracked numbers.

### Labeled test set

`eval/test_set/` contains short code snippets with known issues, and a
manifest declaring the ground truth for each: the expected findings, their
line ranges, and categories. It includes clean snippets with no expected
findings, which test for false positives — flagging a problem in correct
code is as much a failure as missing a real one.

### Scoring

`eval/metrics.py` compares predicted findings against the ground truth
using lenient matching: a prediction counts as correct if it falls within a
small line tolerance of an expected finding and has a compatible category.
Strict equality would be inappropriate given that model output varies
slightly between runs. From the matches it computes true/false positives
and negatives, and from those, precision, recall, and F1.

```python
# precision: of what was reported, how much was correct
# recall:    of what truly exists, how much was found
# F1:        harmonic mean of the two
```

### Running and tracking

`eval/run_eval.py` runs the full pipeline over the test set and reports
per-snippet and aggregate metrics. `eval/mlflow_logger.py` records each run
to MLflow — parameters such as the prompt version and model, the metrics,
and the full results as an artifact — backed locally by SQLite and remotely
by DagsHub for a shareable history.

### Findings from evaluation

Running the suite repeatedly surfaced an important property: with identical
code and prompts, aggregate F1 varied across runs (observed range
approximately 0.67–1.00). This is inherent to non-deterministic model
output. Decomposing the variance showed a clear pattern: clean snippets
never produced false positives, and the primary issue in each snippet was
detected every time; the variance came almost entirely from inconsistent
detection of secondary, subtler issues within the same file.

This has two consequences. First, a single eval run is an unreliable signal
— accuracy must be assessed across multiple runs. Second, the regression
gate must account for variance.

`eval/check_regression.py` therefore flags a regression only when the
current F1 falls below the lowest historically observed score minus a
buffer — "worse than ever seen" rather than "below the best" — preventing
false alarms from ordinary run-to-run noise.

---

## 14. Observability

Two layers of observability operate at different granularities.

LangSmith traces every individual model call with inputs, outputs, latency,
and cost, tagged by tool and finding category. This makes it possible to
filter to, say, every fix-generation call for SQL-injection findings when
debugging, and to see per-call cost — useful for reasoning about the
economics of a review, which involves several sequential model calls per
finding.

MLflow (locally via SQLite, remotely via DagsHub) tracks evaluation runs
over time, so accuracy is a first-class, comparable metric across prompt
versions rather than a number in a console log.

---

## 15. Packaging and deployment

A single Dockerfile builds an image containing the code, dependencies, and
a pre-built vector index, so the container is self-contained and requires
no external storage at runtime. `docker-compose.yml` runs two services from
that image — the API and the web interface — on a shared network, with the
UI reaching the API by service name. The entire stack starts with one
command, which also de-risks cloud deployment, since the deployed artifact
is the same image validated locally.

---

## 16. Validation against real-world code

Beyond the curated test set, the system was run against real pull requests
from well-known open-source projects. It surfaced genuine issues —
including a short-circuit logic error in a conditional, use of a deprecated
hashing algorithm for signing, and a trailing-comma mistake that silently
disabled a test assertion.

It also exposed real limitations worth documenting honestly: in one case an
explanation referenced the wrong web framework, having pattern-matched to a
more common one; in another, a finding's own explanation acknowledged the
code was actually safe yet the finding was still emitted. These are
characteristic LLM failure modes — confident misattribution and
self-inconsistency — and are tracked as targets for prompt refinement,
informed by the evaluation harness.

---

## 17. Design principles in summary

- **One responsibility per module.** Detection, retrieval, prompts, API
  plumbing, and evaluation are independent; changes stay local.
- **A single canonical input shape.** Every interface converges on
  `FileInput`, so the core pipeline is input-agnostic.
- **Validate model output structurally.** Pydantic models catch malformed
  responses at the boundary.
- **Defensive output handling.** Self-repairing JSON parsing and fence
  stripping address real, observed model behaviors.
- **Defense in depth in detection, deduplicated for precision.** Two
  detectors maximize recall; merging overlaps preserves precision.
- **Ground generation in retrieval.** Detection and explanation reference a
  swappable knowledge base, not just parametric knowledge.
- **Decouple frontends from the backend.** The UI uses the API exactly as
  an external client would.
- **Measure, and account for non-determinism.** Accuracy is tracked across
  runs; the regression gate is variance-aware.

---

## 18. Technology stack

| Concern | Technology |
|---|---|
| LLM | Anthropic Claude API |
| Agent orchestration | LangGraph |
| Retrieval | ChromaDB + sentence-transformers |
| Structural parsing | tree-sitter |
| API | FastAPI |
| Web interface | Streamlit |
| Tracing | LangSmith |
| Experiment tracking | MLflow + DagsHub |
| Evaluation | Custom precision/recall/F1 harness |
| Packaging | Docker + Docker Compose |
| Dependency management | uv |
```