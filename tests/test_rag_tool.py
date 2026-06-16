from src.agent.state import BugFinding
from src.tools.rag_tool import get_context_for_finding


def test_get_context_for_sql_injection_finding():
    # We construct a BugFinding by hand here — no need to call the LLM
    # for this test, since we're testing the RAG lookup, not bug detection.
    finding = BugFinding(
        file="example.py",
        line=9,
        severity="critical",
        category="sql_injection",
        description="User input is concatenated directly into a SQL query.",
    )

    context = get_context_for_finding(finding)

    assert context, "Expected at least one context chunk"
    combined = " ".join(context).lower()
    assert "sql" in combined or "parameteri" in combined