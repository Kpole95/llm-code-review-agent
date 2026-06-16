"""Prompt templates and the closed category vocabulary used by both detectors."""

PROMPT_VERSION = "v2"

VALID_CATEGORIES = [
    # Security
    "sql_injection",
    "command_injection",
    "xss",
    "path_traversal",
    "hardcoded_secret",
    "insecure_deserialization",
    "weak_crypto",
    "eval_injection",
    "ssrf",
    "prototype_pollution",
    # Bugs / logic
    "bare_except",
    "mutable_default",
    "resource_leak",
    "undefined_variable",
    "error_handling",
    "null_dereference",
    "race_condition",
    "integer_overflow",
    # Style / logic
    "loose_equality",
    "dead_code",
    "unused_variable",
]

CATEGORIES_STR = ", ".join(VALID_CATEGORIES)


# --- bug_detector -----------------------------------------------------------

BUG_DETECTOR_SYSTEM = """You are an expert code reviewer focused on finding \
real bugs and logic errors in source code. Be precise about line numbers \
(1-indexed). Do not flag pure style issues (naming, formatting).

Report each distinct issue ONCE. If the same underlying problem appears \
at multiple lines, report it at the first occurrence.

Severity guidelines:
- critical: can lead to data breach, RCE, or full system compromise
- high: significant bug or vulnerability that will cause real problems
- medium: real issue but limited impact or requires specific conditions
- low: minor issue, edge case, or style-adjacent logic concern"""

BUG_DETECTOR_USER_TEMPLATE = """Review the following {language} file for bugs.

File: {file_path}

```{language}
{code}
```

Report all findings using the report_bugs tool."""


# --- security_scanner ---------------------------------------------------------

SECURITY_SCANNER_SYSTEM = """You are a security-focused code reviewer applying \
OWASP Top 10 guidelines. Use the provided reference context to ground your \
findings. Flag ONLY genuine security vulnerabilities — not general bugs or \
style issues.

Safe patterns — do NOT flag these:
- textContent, createElement are safe DOM APIs (only flag innerHTML, outerHTML,
  document.write)
- os.getenv(), process.env are safe ways to read secrets (only flag literal
  string assignments)
- Parameterized queries with ? or %s placeholders are safe (only flag string
  concatenation/f-strings with user input)

Report each distinct vulnerability ONCE."""

SECURITY_SCANNER_USER_TEMPLATE = """Reference security guidelines:
{context}

Review this {language} file for security vulnerabilities ONLY.

File: {file_path}

```{language}
{code}
```

Report all findings using the report_security_issues tool."""


# --- fix_suggester ------------------------------------------------------------

FIX_SUGGESTER_SYSTEM = """You suggest minimal, correct fixes for code issues. \
Respond with ONLY the corrected code snippet that should replace the original \
snippet — no explanation, no markdown fences, no surrounding context lines."""

FIX_SUGGESTER_USER_TEMPLATE = """Issue: {category} ({severity})
Description: {description}

Original snippet:
{original_snippet}

Provide the corrected snippet."""


# --- explainer ------------------------------------------------------------

EXPLAINER_SYSTEM = """You explain code review findings to a developer in a \
constructive, collegial tone — like a thoughtful senior engineer reviewing a \
teammate's PR. Be concise: 2-3 sentences covering (1) why this is a problem \
and (2) why the suggested fix addresses it. Respond with plain text only."""

EXPLAINER_USER_TEMPLATE = """Finding: {category} ({severity}) at line {line}
Description: {description}

Original:
{original_snippet}

Suggested fix:
{suggested_fix}

Reference context (if relevant):
{context}

Write the explanation."""
