# Memory

Things I want to remember about this project — gotchas, lessons, context that
doesn't fit cleanly into architecture docs or code comments. Useful for picking
this back up after time away, or for explaining decisions to someone new.

---

## The bugs that cost the most time

**The catch-all exception handler.** There was a `except Exception` in the FastAPI
review route that caught everything and re-raised as a 500 with no detail. When the
ECS deployment broke because the API key was set to a Secrets Manager ARN string
instead of the resolved secret value, CloudWatch showed a 500 with nothing else.
I could see from the logs that the analyze step completed (tree-sitter parsing
printed its summary lines) but the first LLM call failed. Took embarrassingly long
to realize the API key was wrong because there was no trace of the original 401.

Lesson: catch-all handlers need `logger.exception(...)` before the re-raise.
If you can't see the original error from the logs, the handler is hiding information.

**Both ECS containers running Streamlit.** The task definition had two containers
but no per-container command overrides, so both used the `CMD` from the Dockerfile
(which runs uvicorn/FastAPI). The Streamlit container was trying to run the API,
failing silently, and the UI was showing a connection error. Fixed by specifying
the command explicitly for each container in the task definition.

**The Secrets Manager ARN as a literal string.** Related to the first bug but worth
calling out separately. When you use `valueFrom` in an ECS container definition to
pull a secret, ECS resolves it at startup. When you use `value`, it's a literal
string. If you accidentally paste the ARN into a `value` field instead of a
`valueFrom` field, the container gets `arn:aws:secretsmanager:...` as its
`ANTHROPIC_API_KEY`. The Anthropic SDK tries to use that as a key, gets a 401, and
the catch-all handler above hides the detail. I switched to using the literal key
value directly after this.

**Ruff failing on test fixtures.** The test fixtures in `src/eval/test_set/snippets`
and `tests/fixtures` contain intentionally vulnerable code — SQL injection,
hardcoded secrets, eval() calls. Ruff, correctly, flagged all of it. Had to add
both directories to `[tool.ruff] exclude` in `pyproject.toml`. Easy fix once you
know what's happening but confusing when CI fails on code you never intended to lint.

**Nine CI bugs in sequence.** The GitHub Actions workflow broke nine times before
it ran clean. Wrong working directory for the build step. Missing `[dev]`
dependencies in the install step. The ruff fixture issue above. Wrong ECS service
name (copy-pasted from a tutorial). A stale failing run from before the fix that
kept showing as failed on the same commit. Each one was small but they stacked.
The lesson isn't anything deep — it's just that CI pipelines have a lot of moving
parts and you debug them sequentially.

---

## Things that work differently than you'd expect

**LangGraph state and Pydantic.** You can't put Pydantic models directly in
LangGraph state because LangGraph serializes state to JSON between nodes. Pydantic
models aren't JSON-serializable by default (well, you can call `.model_dump()` but
LangGraph doesn't do that for you). The solution is to store findings as plain dicts
in state and convert to `BugFinding` at the start of each node that needs to work
with them. Slightly awkward but not a big deal once you know to expect it.

**ECS same-task networking.** In docker-compose, containers talk to each other by
service name (`http://api:8000`). On ECS Fargate, containers in the same task share
a network namespace, so they talk via localhost (`http://localhost:8000`). The
`API_URL` environment variable has to be set differently for each environment. This
is easy to forget when testing locally with compose and then wondering why the UI
can't reach the API on ECS.

**ChromaDB persistence in Docker.** The vector index needs to be there when the
container starts. The solution (building the index during `docker build`) means the
index is baked into the image. If you update the knowledge base files, you need to
rebuild the image for the changes to take effect. Intuitive once you know it but
not obvious the first time you update a knowledge base file and nothing changes.

**The HuggingFace model download in CI.** `all-MiniLM-L6-v2` downloads on first
use. In CI, this can fail due to network timeouts. The workflow caches the model
files and has a retry loop around the build-index step (three attempts, fifteen
second wait). Without this, CI would fail intermittently on network issues.

---

## Decisions I'm still uncertain about

**The line tolerance in eval matching.** A predicted finding matches an expected one
if it's within two lines of the expected location. Two lines felt right but it's
somewhat arbitrary. A tighter tolerance would increase false negatives (missing
findings that are "close enough"). A looser one would inflate precision. I haven't
run a proper sensitivity analysis on this.

**The semantic dedup threshold (0.82).** Higher means more duplicates slip through.
Lower means more genuine distinct findings get merged. 0.82 came from eyeballing
the distributions in a few runs. It probably needs real calibration.

**Whether to keep the analyze node.** Right now it's informational — it parses
structure and logs it but doesn't gate anything. It exists partly as scaffolding for
a future feature (function-level scoping of findings). If that feature never
materializes, the node is dead weight.

---

## Context that's easy to forget

The eval tuning set is not a secret but it's also not honest to report numbers from
it. Those snippets were used to iterate on prompts and detection logic, so any score
on them is biased by that iteration. The holdout set in `src/eval/holdout/` is the
one that produces honest numbers. The README shows holdout scores. Don't swap them.

The model used in production is `claude-haiku-4-5`, not Sonnet. Haiku is faster and
cheaper. For the structured output use case (forcing tool calls with enums), the
quality difference from Sonnet wasn't meaningful enough to justify the cost.

The ECS service is normally scaled to zero desired tasks. It doesn't cost anything
when it's not running. To bring it up, set desired count to 1 through the console
or CLI. To demo the system, scale up before the demo and scale back down after.

The DagsHub MLflow tracking URI needs credentials (`MLFLOW_TRACKING_USERNAME` and
`MLFLOW_TRACKING_PASSWORD`) in the environment. Without them, MLflow will try to
log locally. This is only relevant if you're running evals and care about logging
to DagsHub — local runs are fine without it.

---

## What I'd do differently

Start with the eval harness. I built detection first, then evaluation. The right
order is the opposite: define what "correct" means, build the measurement, then
build the thing being measured. I knew this in principle and still got it backwards.

Add `.env.example` from day one. It's a ten-minute task and it makes the repo
dramatically easier to pick up from scratch. I kept meaning to add it and finally
did it late in the project.

Be more conservative with the knowledge base structure. The markdown files grew
organically and their chunking isn't perfect — some chunks are too small to be
useful context, others cross section boundaries awkwardly. A cleaner initial
structure would have saved some retrieval quality issues.
