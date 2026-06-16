"""
Tests bug_detector against our known-buggy fixture.

@pytest.mark.skipif: this test calls the REAL Claude API (costs a tiny
amount, takes a few seconds). We skip it automatically if no API key is
set, e.g. in some CI environments — but locally it WILL run since you have
a key in .env.
"""
import os
import pytest

from src.tools.bug_detector import detect_bugs

FIXTURE_PATH = "tests/fixtures/sql_injection.py"


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="No API key configured")
def test_detect_sql_injection():
    with open(FIXTURE_PATH) as f:
        code = f.read()

    findings = detect_bugs(code, "python", FIXTURE_PATH)

    assert findings, "Expected at least one finding"

    categories = [f.category.lower() for f in findings]
    # We don't assert an EXACT category string (Claude might say
    # "sql_injection" or "sqli" or "injection") — we check that SOMETHING
    # in the categories mentions "sql" or "inject".
    assert any("sql" in c or "inject" in c for c in categories)