"""Security-focused detection: deterministic regex checks plus an OWASP-grounded LLM scan."""
import re

from src.agent.llm_client import chat_tool
from src.agent.prompts import (
    SECURITY_SCANNER_SYSTEM,
    SECURITY_SCANNER_USER_TEMPLATE,
    VALID_CATEGORIES,
)
from src.agent.state import BugFinding
from src.rag.retriever import retrieve_context

_SECURITY_SCANNER_TOOL = {
    "name": "report_security_issues",
    "description": (
        "Report all security vulnerabilities found in the code. "
        "Call this tool with every finding, including an empty array if none are found."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "description": "List of security findings. Empty array if none.",
                "items": {
                    "type": "object",
                    "properties": {
                        "line": {
                            "type": "integer",
                            "description": "1-indexed line number of the issue",
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["low", "medium", "high", "critical"],
                        },
                        "category": {
                            "type": "string",
                            "enum": VALID_CATEGORIES,
                        },
                        "description": {
                            "type": "string",
                            "description": "One sentence describing the vulnerability",
                        },
                        "original_snippet": {
                            "type": "string",
                            "description": "The exact vulnerable line(s)",
                        },
                    },
                    "required": ["line", "severity", "category", "description"],
                },
            }
        },
        "required": ["findings"],
    },
}

_SECRET_PATTERN = re.compile(
    r"(?i)[A-Za-z_][A-Za-z0-9_]*(secret|api[_-]?key|password|token|credential)"
    r"[A-Za-z0-9_]*\s*=\s*[\"'][^\"']{8,}[\"']"
)
_EVAL_PATTERN = re.compile(r"\beval\s*\(")
_EXEC_PATTERN = re.compile(r"\bexec\s*\(")


def _regex_findings(code: str, file_path: str) -> list[BugFinding]:
    """Deterministic, zero-cost checks for obvious secrets and eval/exec usage."""
    findings = []
    for lineno, line in enumerate(code.splitlines(), start=1):
        if _SECRET_PATTERN.search(line):
            findings.append(BugFinding(
                file=file_path,
                line=lineno,
                severity="high",
                category="hardcoded_secret",
                description="Line matches a pattern for a hardcoded credential or secret.",
                original_snippet=line.strip(),
            ))
        if _EVAL_PATTERN.search(line) or _EXEC_PATTERN.search(line):
            findings.append(BugFinding(
                file=file_path,
                line=lineno,
                severity="critical",
                category="eval_injection",
                description=(
                    "eval()/exec() executes arbitrary strings as code — "
                    "a code injection risk if input is untrusted."
                ),
                original_snippet=line.strip(),
            ))
    return findings


def _llm_findings(code: str, language: str, file_path: str) -> list[BugFinding]:
    """OWASP-grounded LLM scan using a schema-enforced tool call."""
    context_chunks = retrieve_context("OWASP top 10 security vulnerabilities", k=3)
    context = "\n---\n".join(context_chunks)

    prompt = SECURITY_SCANNER_USER_TEMPLATE.format(
        context=context, language=language, file_path=file_path, code=code
    )

    result = chat_tool(
        prompt,
        tool=_SECURITY_SCANNER_TOOL,
        system=SECURITY_SCANNER_SYSTEM,
        max_tokens=2048,
        tags=["security_scanner"],
        metadata={"file": file_path, "language": language},
    )

    findings = []
    for item in result.get("findings", []):
        try:
            findings.append(BugFinding(
                file=file_path,
                line=item["line"],
                severity=item["severity"],
                category=item["category"],
                description=item["description"],
                original_snippet=item.get("original_snippet"),
                context_docs=context_chunks,
            ))
        except (KeyError, TypeError):
            continue

    return findings


def scan_security(code: str, language: str, file_path: str) -> list[BugFinding]:
    return _regex_findings(code, file_path) + _llm_findings(code, language, file_path)
