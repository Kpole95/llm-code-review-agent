import os
import pytest

from src.agent.state import BugFinding
from src.tools.explainer import explain_finding


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="No API key configured")
def test_explain_sql_injection_finding():
    finding = BugFinding(
        file="db.py",
        line=9,
        severity="critical",
        category="sql_injection",
        description="SQL query built via f-string with unsanitized user input.",
        original_snippet='query = f"SELECT * FROM users WHERE email=\'{email}\'"',
        suggested_fix='query = "SELECT * FROM users WHERE email = %s"\ncursor.execute(query, (email,))',
        context_docs=[
            "Never build SQL via string concatenation/f-strings with user "
            "input. Use parameterized queries instead."
        ],
    )

    explanation = explain_finding(finding)

    assert explanation
    assert not explanation.startswith("```")
    # A reasonable explanation should be more than a one-word answer,
    # but also not an essay — roughly sentence-length.
    assert 20 < len(explanation) < 800