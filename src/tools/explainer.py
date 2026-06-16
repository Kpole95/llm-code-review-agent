"""Generates a short human-readable explanation for a finding."""
from src.agent.llm_client import _strip_fences, chat
from src.agent.prompts import EXPLAINER_SYSTEM, EXPLAINER_USER_TEMPLATE
from src.agent.state import BugFinding


def explain_finding(finding: BugFinding) -> str:
    """Requires original_snippet, suggested_fix, and context_docs to already be set."""
    context = "\n---\n".join(finding.context_docs) if finding.context_docs else "(none)"

    prompt = EXPLAINER_USER_TEMPLATE.format(
        category=finding.category,
        severity=finding.severity,
        line=finding.line,
        description=finding.description,
        original_snippet=finding.original_snippet or "",
        suggested_fix=finding.suggested_fix or "",
        context=context,
    )

    raw = chat(
        prompt,
        system=EXPLAINER_SYSTEM,
        max_tokens=256,
        tags=["explainer", finding.category],
        metadata={"file": finding.file, "line": finding.line, "severity": finding.severity},
    ).strip()
    return _strip_fences(raw)
