"""Generates a suggested code fix for a finding."""
from src.agent.llm_client import _strip_fences, chat
from src.agent.prompts import FIX_SUGGESTER_SYSTEM, FIX_SUGGESTER_USER_TEMPLATE
from src.agent.state import BugFinding


def suggest_fix(finding: BugFinding) -> str:
    """Given a finding with original_snippet set, return a corrected snippet as plain text."""
    prompt = FIX_SUGGESTER_USER_TEMPLATE.format(
        category=finding.category,
        severity=finding.severity,
        description=finding.description,
        original_snippet=finding.original_snippet or "",
    )
    raw = chat(
        prompt,
        system=FIX_SUGGESTER_SYSTEM,
        max_tokens=512,
        tags=["fix_suggester", finding.category],
        metadata={"file": finding.file, "line": finding.line, "severity": finding.severity},
    ).strip()
    return _strip_fences(raw)
