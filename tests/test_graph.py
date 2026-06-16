import os
import pytest

from src.agent.graph import run_review

FIXTURE_PATH = "tests/fixtures/sql_injection.py"


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="No API key configured")
def test_run_review_end_to_end():
    with open(FIXTURE_PATH) as f:
        code = f.read()

    findings = run_review([{"path": FIXTURE_PATH, "content": code, "language": "python"}])

    assert findings, "Expected at least one finding"
    for finding in findings:
        # Every finding should have been enriched with context by enrich_node
        assert "context_docs" in finding
        assert isinstance(finding["context_docs"], list)