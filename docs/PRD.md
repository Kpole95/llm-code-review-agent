# Product Requirements Document

## Why this exists

Code review is expensive. A senior engineer doing a careful security review of a
pull request is spending time they could be spending on architecture, mentoring, or
shipping features. For solo developers or small teams, that review often just doesn't
happen, and vulnerabilities slip in not because anyone is careless but because there
aren't enough hours.

The idea behind this project was simple: what if you could get a first-pass review
on every file before a human ever looked at it? Not a replacement for a real review,
but a filter — something that catches the obvious stuff (hardcoded secrets, SQL
injection, unsafe deserialization) so the human reviewer can focus on the things that
actually require judgment.

There are commercial tools that do this. CodeRabbit, Snyk, Semgrep. This project
is not trying to compete with them at scale. It started as a way to understand how
you'd actually build something like that — from the detection logic to the evaluation
to the deployment — and turned into a production system I'm genuinely happy to run
against my own code.

---

## Who uses it

Right now, mostly me. But the system is built for any developer who wants a second
opinion on code before it goes into review. The three interfaces (CLI for local dev,
API for integration, Streamlit for demos) cover the main ways someone would reach for
a tool like this.

The most useful mode in practice is the GitHub PR URL — you paste a PR link and get
findings without ever cloning the repo.

---

## What it needs to do

The core requirement is simple: given a code file, tell me what's wrong with it. The
details matter a lot though.

**Findings need to be specific.** "This code has a security issue" is useless.
"Line 47, SQL query built with string concatenation — here's the parameterized
version that fixes it" is useful. Every finding needs a file, a line, a severity,
a category, a snippet of the original code, a suggested fix, and an explanation in
plain English.

**It needs to be honest about what it finds.** A system that flags everything as
critical to look thorough is worse than useless — you stop trusting it. The severity
vocabulary is fixed (low/medium/high/critical) and the category vocabulary is fixed
too. The model can't invent categories to sound smarter.

**It needs to be evaluable.** I wanted to actually know how well it works, not just
have a vague sense that "the outputs look good." That meant building an eval harness
with a hold-out set from the beginning, not as an afterthought.

**Five languages at minimum.** Python and JavaScript cover most of what I write.
TypeScript, Java, and Go make it useful for a broader set of codebases.

**Deployed, not just runnable locally.** A portfolio project that only works on your
laptop is a demo, not a system. The target was ECS Fargate with a CI/CD pipeline.

---

## What it doesn't need to do

It's not a full static analysis tool. It won't catch every possible issue, and it
won't replace a linter like ruff or ESLint for style issues. It's not meant to.

It doesn't need to handle private repositories. The GitHub loader only works with
public PRs. Adding OAuth and token handling is the obvious next step but wasn't in
scope.

It's not a real-time review bot that automatically comments on PRs. That's a
product feature. What's here is the detection engine that would power something
like that.

---

## How to know if it's working

The number I care about most is the hold-out F1. Not the tuning-set F1, because
that number is biased by the iteration that produced it. The hold-out set is ten
labeled snippets the system never saw during development, and the F1 on those runs
is 0.78–0.95 depending on the run.

I report it as a range because the model is non-deterministic. Reporting a single
number would be misleading. The honest story is that it finds real issues reliably,
with some variance.

The other thing I check is whether the suggested fixes are actually correct. An
eval harness can tell you whether findings were detected but not whether the fix is
good. That part still requires a human eye.

---

## Constraints that shaped everything

**No training data.** Fine-tuning would have been the "obvious" approach if I had
thousands of labeled code review examples. I didn't. RAG on an OWASP knowledge base
is what you do when you have domain knowledge but no labeled data.

**API costs matter.** Every finding in the enrich step costs two LLM calls (fix +
explanation). With ten findings per file that's twenty calls. Parallelizing
enrichment was necessary to keep latency reasonable; capping the thread pool was
necessary to keep costs reasonable.

**The model can hallucinate.** This is just true. Forced tool use with schema
validation gets you structured output you can depend on, but it doesn't make the
model's judgment correct. The regex detector is there partly to catch the cases
where the LLM misses something obvious, and deduplication is there to handle the
cases where it catches the same thing twice.
