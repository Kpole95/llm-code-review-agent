# Design

The decisions that shaped how this system is built, and the reasoning behind them.
Some of these were planned from the start. Others only became clear after something
didn't work.

---

## Why LangGraph instead of a plain function

The pipeline has three stages that run in order: parse, detect, enrich. You could
implement that as three function calls in a row. I chose LangGraph because it gives
you explicit state management, a clear graph topology you can inspect, and a natural
checkpoint mechanism if you want to resume from a specific node.

More practically, it made the architecture legible. When someone looks at `graph.py`
they see `analyze → detect → enrich → END` and immediately understand the shape of
the system. A chain of function calls is harder to read at that level of abstraction.

The tradeoff is that LangGraph has opinions about state shape (TypedDict, JSON-
serializable) that add a small amount of ceremony. The dict/Pydantic round-trip in
nodes is a direct result of this. It's a reasonable price.

---

## Why RAG instead of fine-tuning

I didn't have training data. Fine-tuning is the right answer when you have thousands
of labeled examples of the thing you want the model to do. I had a knowledge base
of OWASP guidance and language best practices. RAG is what you do in that situation.

Beyond the data question, RAG has some properties that make it genuinely better for
this use case even if you had training data. The knowledge is external and inspectable
— you can see exactly which chunks were retrieved for a finding. Updating the
knowledge base (new OWASP guidance, a new language's best practices) means editing
a markdown file and rebuilding the index, not retraining a model. And RAG doesn't
sacrifice the model's general code understanding the way fine-tuning can.

---

## Why two detectors

The bug detector and the security scanner cover overlapping ground intentionally.
A hardcoded AWS key is both a bug and a security vulnerability. Having two detectors
catch it independently, with deduplication to merge the results, gives better recall
than either detector alone.

The security scanner also has a two-layer design of its own: a deterministic regex
pass runs first, then an LLM-based pass with RAG context. The regex catches obvious
things (patterns that match `AKIA...` for AWS keys, `eval()` calls) with zero cost
and zero false negatives for those patterns. The LLM handles the cases that are
contextually ambiguous.

The explicit design here is defense in depth. No single layer is supposed to catch
everything. They're supposed to catch different things and overlap on the obvious
cases.

---

## Why forced tool use

Early versions asked the model for JSON and then parsed the output. This was fragile.
The model would sometimes wrap the JSON in markdown fences, sometimes add a
preamble, sometimes use a slightly different key name. Each of those required a
workaround.

Forced tool use (`tool_choice: {"type": "tool", "name": "report_bugs"}`) makes the
API guarantee the response matches the schema. `severity` is an enum — the model
can't return `"high-critical"` or `"urgent"`. `category` is drawn from the fixed
vocabulary. The `required` array ensures fields that downstream logic depends on are
always present.

The schema acts as a contract. Code that processes findings can assume the contract
holds without defensive checks at every field access.

---

## Why composite embeddings for deduplication

The semantic dedup pass uses `category + description` as the string to embed, not
just `description`. This took a few iterations to get right.

The original approach embedded only the description. The problem was that two
detectors describing the same issue used different language — one might say "AWS
secret key is hardcoded at line 47" and another might say "Line 47 matches a pattern
for a hardcoded credential." These descriptions aren't very similar in embedding
space even though they're pointing at the same thing.

Adding the category as a prefix anchors the embedding to the type of finding. Two
descriptions of the same SQL injection at the same line will have `sql_injection`
in front of both, which pushes their embeddings close together even if the prose
is different.

The embeddings are computed once outside the comparison loop. The first version
computed them inside the loop, which caused latency spikes on files with many
findings.

---

## Why the RAG index builds at image build time

The alternative is to build it at container startup. The problem with that is
startup latency — building the index takes a few seconds, which means the first
request after a cold start has to wait. More importantly, build-time failures fail
loudly in CI; startup-time failures fail quietly in production when a request comes
in.

The index is built from files in `knowledge_base/` which are committed to the repo.
They don't change at runtime. Building them into the image is the right model.

---

## Why the Streamlit UI calls the API over HTTP

The UI and the API are separate containers in the same ECS task. The UI could
theoretically import `run_review` directly, but that would mean it needs the
Anthropic API key, the ChromaDB data, and all the model dependencies. As a separate
process calling the API, it only needs to know the API URL.

This also means the UI and the API can be scaled independently, deployed separately,
or swapped for different implementations without touching each other. In the current
setup this doesn't matter much (they're in the same task), but it's the right
boundary to maintain.

Note: on ECS Fargate, containers in the same task share a network namespace, so
the UI reaches the API at `http://localhost:8000`. In docker-compose it's
`http://api:8000`. These are different values in the same environment variable
slot — something to be careful about when switching between local and ECS.

---

## Why `all-MiniLM-L6-v2` for embeddings

It's fast, small (22M parameters), runs locally without any API calls, and produces
good enough embeddings for the retrieval task at hand. The knowledge base is a few
hundred chunks of structured security guidance — this isn't a case where you need a
frontier embedding model.

The alternative would be an API-based embedding (Anthropic, OpenAI) that costs money
per call. For a knowledge base that doesn't change frequently, paying per-query for
embeddings made no sense when a local model works fine.

---

## The evaluation methodology

The single most important methodological decision was the tuning set / hold-out
split. I decided early that whatever number I reported publicly had to come from data
the system had never influenced through iteration. The tuning set is what you iterate
against. The hold-out set is sealed until you want to produce a number worth quoting.

The F1 is reported as a range (0.78–0.95) rather than a single number because LLM
outputs are non-deterministic. Running the same hold-out set twice gives different
results. A single number would imply a precision the measurement doesn't have.

The other honest caveat: the hold-out snippets are controlled single-issue examples.
Real code files are longer, messier, and have multiple interacting issues. The eval
measures whether the system finds what it's supposed to find in clean conditions. It
doesn't measure performance on production codebases.
