"""FastAPI service — HTTP front-door for the pipeline."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.agent.graph import run_review

app = FastAPI(title="LLM Code Review Agent", version="0.1.0")


class FileInput(BaseModel):
    path: str
    content: str
    language: str


class ReviewRequest(BaseModel):
    files: list[FileInput]


class Finding(BaseModel):
    """API-facing mirror of BugFinding, kept separate so the public contract
    stays stable even if internal pipeline fields change."""
    file: str
    line: int
    severity: str
    category: str
    description: str
    original_snippet: str | None = None
    suggested_fix: str | None = None
    explanation: str | None = None


class ReviewResponse(BaseModel):
    findings: list[Finding]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/review", response_model=ReviewResponse)
def review(request: ReviewRequest):
    if not request.files:
        raise HTTPException(status_code=422, detail="At least one file is required.")

    try:
        files = [f.model_dump() for f in request.files]
        findings = run_review(files)
        return ReviewResponse(findings=findings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review failed: {e}")
