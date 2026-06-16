"""Shared data shapes used across the pipeline."""
from typing import Optional, TypedDict
from pydantic import BaseModel, Field


class FileInput(TypedDict):
    """One file being reviewed."""
    path: str
    content: str
    language: str


class BugFinding(BaseModel):
    """One review finding, filled in incrementally as it moves through the pipeline."""
    file: str
    line: int
    severity: str = Field(description="one of: low, medium, high, critical")
    category: str = Field(description="short snake_case tag, e.g. sql_injection")
    description: str

    original_snippet: Optional[str] = None
    suggested_fix: Optional[str] = None
    explanation: Optional[str] = None
    context_docs: list[str] = Field(default_factory=list)


class AgentState(TypedDict, total=False):
    """State object passed between pipeline stages."""
    files: list[FileInput]
    findings: list[dict]
