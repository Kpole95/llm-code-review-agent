import os
import pytest

from src.agent.state import BugFinding
from src.tools.fix_suggester import suggest_fix


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="No API key configured")
def test_suggest_fix_for_sql_injection():
    # Hand-built finding — we're testing fix_suggester in isolation,
    # not the full detection pipeline.
    finding = BugFinding(
        file="db.py",
        line=9,
        severity="critical",
        category="sql_injection",
        description="SQL query built via f-string with unsanitized user input.",
        original_snippet='query = f"SELECT * FROM users WHERE email=\'{email}\'"',
    )

    fix = suggest_fix(finding)

    assert fix, "Expected a non-empty fix"
    # The fix should move toward parameterization — i.e. NOT still
    # contain the raw f-string interpolation of `email` into the query.
    assert "{email}" not in fix
    # A parameterized query uses a placeholder like ? or %s
    assert "?" in fix or "%s" in fix
    assert not fix.startswith("```")
    assert "```" not in fix
    assert not fix.lower().startswith("python")