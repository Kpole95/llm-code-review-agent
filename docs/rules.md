# Rules

These are the decisions that are locked in. Not guidelines you can ignore if you
have a good reason — actual rules, the kind where deviating from them will break
something or make future work significantly harder. Most of them were learned the
hard way.

---

## The pipeline has one entry point

`run_review(files)` in `src/agent/graph.py` is the only place review logic lives.
The CLI calls it. The API calls it. The Streamlit UI calls it (via the API). Nothing
else reviews code.

If you're tempted to add review logic somewhere else — directly in the API route,
or in the UI for a quick test — don't. The reason this rule exists is that before it
was enforced, the CLI and the API had diverged and were producing different results
for the same input. It took a while to notice and longer to untangle.

---

## Categories and languages are defined once

`VALID_CATEGORIES` in `src/agent/prompts.py` is the only place bug categories are
defined. `EXT_LANG` in `src/parsing/pr_loader.py` is the only place supported file
extensions and their language names are defined.

Adding a language or a category means touching exactly one place. If you find
yourself copying a language name or a category string anywhere else in the codebase,
stop — you're about to create a drift problem. The Streamlit language dropdown
hardcoding bug (`["python", "javascript"]` that never got updated) is what this rule
prevents from happening again.

---

## All model calls go through `llm_client.py`

`chat()`, `chat_json()`, and `chat_tool()` are the only functions that talk to the
Anthropic API. Every caller goes through one of these three.

The reason is observability. The client is wrapped with `wrap_anthropic()` from
LangSmith, which traces every call automatically. If you make a direct
`anthropic.Anthropic().messages.create()` call somewhere in the tools, that call
is invisible in LangSmith. Debugging production issues without traces is painful
enough that this rule is worth enforcing strictly.

---

## Findings are dicts inside state, Pydantic objects everywhere else

LangGraph's state needs to be JSON-serializable. Pydantic models aren't, directly.
So inside `AgentState`, findings live as plain dicts. When a node needs to work with
a finding, it converts to a `BugFinding` object for validation and then back to a
dict before writing to state.

This pattern looks slightly awkward at first. It's the right tradeoff. The
alternative (custom serializers, or giving up on Pydantic) creates more problems than
the dict/model round-trip.

---

## Never catch bare exceptions in route handlers without logging

This was the root cause of the hardest debugging session in this project. A
catch-all `except Exception` in the FastAPI review route was re-raising as a 500,
but swallowing the original traceback. CloudWatch showed a 500, nothing else.

Every catch-all needs `logger.exception("...")` or `logger.error(exc_info=True)`
before the re-raise. If you can't see what went wrong from the logs, the catch
is making things worse, not better.

---

## Hold-out set is read-only

`src/eval/holdout/` is never used during prompt iteration, detector changes, or
threshold tuning. It's only run to produce the number that gets reported publicly.

The tuning set (`src/eval/test_set/`) is what you use while working. If you run
against holdout to check a change and it improves, that's fine — but you've now
burned that holdout sample for measuring unbiased performance. The moment you start
making decisions based on holdout scores, the holdout is no longer honest.

---

## Don't add semantic dedup without also adding exact-match dedup first

When I first added semantic deduplication (cosine similarity on embeddings), it
missed exact duplicates because the similarity threshold had wiggle room. Exact
match on `(file, line, category)` needs to run first — it's cheap and catches the
most common case. Semantic dedup is the second pass for the cases exact match misses.

Running them in the wrong order or skipping exact match makes the semantic pass do
more work than it needs to and introduces noise.

---

## The RAG index is built at Docker image build time, not at startup

`build_index` runs during `docker build`, not when the container starts. This means:

1. The container is ready immediately when it comes up — no startup delay waiting
   for the index to build.
2. If `build_index` fails, the image build fails. You find out during CI, not when
   the container is running and the first request comes in.

Don't move the index build to startup unless you have a very good reason. The
current approach makes failures loud and early.

---

## The HTML scrubber is a safety net, not the primary defense

The scrubber in `enrich_node` exists to catch UI template leakage that shouldn't
happen if the prompts are working correctly. It's not a substitute for prompt-level
constraints.

If you're seeing a lot of scrubber activity in the logs, the fix is the prompt, not
the scrubber. The scrubber is deliberately narrow — it only removes tags with the
app's own CSS class names — and intentionally does nothing when it doesn't see
leakage markers. Making it more aggressive risks destroying legitimate code in
snippets.
