"""General bug detection via a schema-enforced LLM tool call."""
from src.agent.llm_client import chat_tool
from src.agent.prompts import BUG_DETECTOR_SYSTEM, BUG_DETECTOR_USER_TEMPLATE, VALID_CATEGORIES
from src.agent.state import BugFinding

_BUG_DETECTOR_TOOL = {
    "name": "report_bugs",
    "description": (
        "Report all bugs and logic errors found in the code. "
        "Call this tool with every finding, including an empty array if no bugs are found."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "description": "List of bugs found. Empty array if none.",
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
                            "description": "One sentence describing the issue",
                        },
                        "original_snippet": {
                            "type": "string",
                            "description": "The exact problematic line(s), raw code only",
                        },
                    },
                    "required": ["line", "severity", "category", "description", "original_snippet"],
                },
            }
        },
        "required": ["findings"],
    },
}


def detect_bugs(code: str, language: str, file_path: str) -> list[BugFinding]:
    """Ask Claude to find bugs; the tool schema guarantees valid categories/severities."""
    prompt = BUG_DETECTOR_USER_TEMPLATE.format(language=language, file_path=file_path, code=code)

    result = chat_tool(
        prompt,
        tool=_BUG_DETECTOR_TOOL,
        system=BUG_DETECTOR_SYSTEM,
        max_tokens=2048,
        tags=["bug_detector"],
        metadata={"file": file_path, "language": language},
    )

    findings = []
    for item in result.get("findings", []):
        try:
            findings.append(
                BugFinding(
                    file=file_path,
                    line=item["line"],
                    severity=item["severity"],
                    category=item["category"],
                    description=item["description"],
                    original_snippet=item.get("original_snippet"),
                )
            )
        except (KeyError, TypeError):
            continue

    return findings