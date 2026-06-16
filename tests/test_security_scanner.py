import os
import pytest

from src.tools.security_scanner import scan_security, _regex_findings

CONFIG_PATH = "tests/fixtures/sample_pr/config.py"


def test_regex_catches_hardcoded_secret_without_llm():
    """The regex check alone (no API call) should catch the obvious secret."""
    with open(CONFIG_PATH) as f:
        code = f.read()

    findings = _regex_findings(code, CONFIG_PATH)
    categories = [f.category for f in findings]
    assert "hardcoded_secret" in categories


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="No API key configured")
def test_full_scan_finds_secret():
    with open(CONFIG_PATH) as f:
        code = f.read()

    findings = scan_security(code, "python", CONFIG_PATH)
    assert findings
    assert any("secret" in f.category.lower() or "credential" in f.category.lower() for f in findings)