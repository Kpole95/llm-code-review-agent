# Phases

How this project actually got built, in order. Not a tidy retrospective — more like
a working log of what happened, what broke, and what changed.

---

## Phase 1 — Getting a signal

The first version was about twenty lines of Python. It took a hardcoded snippet,
sent it to the Claude API with a prompt saying "find bugs in this code," and printed
the response. No structure, no eval, no deployment — just a sanity check that the
model could actually do this.

It could. The output was messy free text, but the bugs it found were real. That was
enough to justify building something proper.

---

## Phase 2 — Structure

Free text is useless in a pipeline. You can't sort it, filter it, or display it in
a UI without parsing it, and parsing LLM free text is fragile. So the second thing
I built was forced tool use — a JSON schema with enums for severity and category
that the API would enforce on the model's output.

This is when `VALID_CATEGORIES` and `BugFinding` came into existence. The category
list started with about twelve entries and grew from there as I hit cases it didn't
cover. The severity enum (`low/medium/high/critical`) hasn't changed since the
beginning.

Forced tool use also meant the outputs were actually Pydantic-validatable, which
made it possible to write code downstream that depended on specific field types
without constant `isinstance` checks.

---

## Phase 3 — RAG

The model was finding generic issues but missing context-specific ones. An SQL
injection detection that doesn't know what parameterized queries look like in the
language it's reviewing isn't that useful.

Adding RAG meant building a knowledge base first. I wrote out the OWASP LLM Top 10
and some language-specific best practice notes as markdown, chunked them with
`RecursiveCharacterTextSplitter`, embedded them with `all-MiniLM-L6-v2` (local,
no per-call cost), and stored the vectors in ChromaDB. Then I wired retrieval into
the security scanner so the prompt always included the two or three most relevant
knowledge base chunks.

The retrieval query was originally just the finding's description. Later changed to
`category + description` composite, which gave sharper retrieval because the category
anchors what kind of thing you're looking for.

---

## Phase 4 — Multiple languages

Python-only was fine for proving the concept but not useful enough to call a real
system. JavaScript came next because it was the closest to Python in terms of syntax
patterns. TypeScript, Java, and Go followed.

Each language addition touched two files: `code_parser.py` (adding the tree-sitter
grammar and node type maps) and `pr_loader.py` (adding the extension mapping). The
first time I added a language I also had to update the Streamlit dropdown, which was
hardcoded to `["python", "javascript"]`. Fixed that by deriving the dropdown from
`EXT_LANG` so it updates automatically.

---

## Phase 5 — Three interfaces

The first interface was the CLI, which is still the one I use most for development.
The FastAPI service came next, primarily so there was a proper HTTP interface to
build the UI against. The Streamlit UI came last — it's the demo-friendly surface,
the one that works without installing anything.

All three call `run_review()`. Getting to that single entry point took a refactor —
early versions had some logic duplicated between the CLI and the API that drifted
out of sync. The refactor was annoying but worth it.

---

## Phase 6 — Eval

I had been informally checking whether outputs looked right. That's not enough. I
built the eval harness — a set of labeled snippets with expected findings, a metrics
module that computes precision/recall/F1 against expected outputs, and MLflow logging
so each run was tracked.

The first real eval run against the holdout set came in at F1 0.55. Precision was
terrible — 0.38 — even though recall was nearly 1.0. The reason was deduplication,
or the lack of it. The two detectors were flagging the same issues independently,
and both were counting against the same expected finding, creating false positives.

This is when deduplication became a priority. Exact match first, then semantic.
F1 went to 0.78–0.95 after that.

---

## Phase 7 — Deployment

Getting the CI working took longer than expected. Nine bugs in sequence, mostly in
the GitHub Actions config — wrong working directory, missing dev dependencies in the
build, ruff failing on intentionally vulnerable test fixtures (fixed with
`exclude` in pyproject.toml), wrong ECS service name, stale run showing old failures.

The ECS deployment had its own issues. Both containers were running Streamlit because
there were no per-container command overrides in the task definition — the default
CMD from the Dockerfile ran in both. Fixed by specifying commands per container.

The worst one was the API key. The ECS container was receiving the Secrets Manager
ARN as a literal string instead of the resolved secret value. The catch-all exception
handler in the FastAPI route was swallowing the traceback, so CloudWatch showed a
500 with no detail. Took a while to work backward from the log showing the analyze
step completing to realizing the first LLM call was failing with a 401.

After that, the deployment worked. The service runs at zero desired tasks when idle
(no cost) and scales to one for demos.

---

## Phase 8 — Cleanup and polish

After the system was running, I spent time on the things that matter for a project
people might actually look at: parallel enrichment (sequential was too slow),
the HTML scrubber (template leakage into snippet fields), a proper `.env.example`,
CONTRIBUTING.md, issue templates, dependabot config, updating the pyproject.toml
metadata. The kind of work that isn't exciting but makes the difference between a
project that looks half-finished and one that looks considered.

The RepoGrade score went from 80 to 100 during this phase.

---

## What's next

A few things I know are missing:

The GitHub loader only works with public PRs. OAuth would make it work with private
repos, which is where most real code lives.

Bedrock integration — the system currently calls Claude through the Anthropic API
directly. There's a natural version that routes through AWS Bedrock instead, which
would be useful for teams that are already in the AWS ecosystem.

Kubernetes deployment — the current ECS setup works but K8s manifests would make
it easier to run in more environments.

Better multi-file analysis — right now each file is reviewed independently. A lot
of real bugs span files (a function defined in one file called incorrectly in
another). That's a harder problem.
