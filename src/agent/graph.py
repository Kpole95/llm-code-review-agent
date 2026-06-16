"""LangGraph pipeline: analyze -> detect -> enrich."""
import numpy as np
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from langgraph.graph import END, StateGraph

from src.agent.state import AgentState, BugFinding
from src.parsing.code_parser import parse_file
from src.tools.bug_detector import detect_bugs
from src.tools.explainer import explain_finding
from src.tools.fix_suggester import suggest_fix
from src.tools.rag_tool import get_context_for_finding
from src.tools.security_scanner import scan_security

_embed_fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom < 1e-8:
        return 0.0
    return float(np.dot(a, b) / denom)


def deduplicate_findings(findings, line_tolerance=3, similarity_threshold=0.82):
    """
    Merge duplicate findings in two passes: an exact match on
    (file, line, category), then a semantic pass on description similarity
    for near-duplicates the exact pass misses.
    """
    if not findings:
        return []

    seen = {}
    pre_deduped = []
    for f in findings:
        key = (f.file, f.line, f.category)
        if key not in seen:
            seen[key] = f
            pre_deduped.append(f)
        else:
            existing = seen[key]
            if _SEVERITY_RANK.get(f.severity, 0) > _SEVERITY_RANK.get(existing.severity, 0):
                idx = pre_deduped.index(existing)
                pre_deduped[idx] = f
                seen[key] = f

    if len(pre_deduped) == 1:
        return pre_deduped

    descriptions = [f.description for f in pre_deduped]
    embeddings = np.array(_embed_fn(descriptions))

    merged = set()
    kept = []
    for i, f in enumerate(pre_deduped):
        if i in merged:
            continue
        group = [f]
        for j, g in enumerate(pre_deduped):
            if j <= i or j in merged:
                continue
            if f.file != g.file:
                continue
            if abs(f.line - g.line) > line_tolerance:
                continue
            sim = _cosine_similarity(embeddings[i], embeddings[j])
            if sim > similarity_threshold:
                merged.add(j)
                group.append(g)
        best = max(group, key=lambda x: _SEVERITY_RANK.get(x.severity, 0))
        kept.append(best)

    return kept


def analyze_node(state: AgentState) -> AgentState:
    """Parse each file's structure. Informational only — detection runs regardless."""
    for f in state["files"]:
        try:
            parsed = parse_file(f["content"], f["language"])
            print(f"[analyze] {f['path']}: {len(parsed.functions)} function(s), {parsed.loc} LOC")
        except ValueError:
            print(f"[analyze] {f['path']}: skipped (unsupported language)")
    return state


def detect_node(state: AgentState) -> AgentState:
    """Run both detectors on every file, then deduplicate the combined findings."""
    all_findings: list[BugFinding] = []
    for f in state["files"]:
        all_findings.extend(detect_bugs(f["content"], f["language"], f["path"]))
        all_findings.extend(scan_security(f["content"], f["language"], f["path"]))

    deduped = deduplicate_findings(all_findings)
    state["findings"] = [finding.model_dump() for finding in deduped]
    return state


def enrich_node(state: AgentState) -> AgentState:
    """For each finding: attach context, then a fix, then an explanation (in order)."""
    enriched = []
    for raw in state["findings"]:
        finding = BugFinding(**raw)

        if not finding.context_docs:
            finding.context_docs = get_context_for_finding(finding)

        if finding.original_snippet:
            finding.suggested_fix = suggest_fix(finding)
            finding.explanation = explain_finding(finding)

        enriched.append(finding.model_dump())

    state["findings"] = enriched
    return state


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("analyze", analyze_node)
    graph.add_node("detect", detect_node)
    graph.add_node("enrich", enrich_node)
    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "detect")
    graph.add_edge("detect", "enrich")
    graph.add_edge("enrich", END)
    return graph.compile()


_compiled_graph = build_graph()


def run_review(files: list[dict]) -> list[dict]:
    """Entry point used by cli.py, api/main.py, and the eval runners."""
    result = _compiled_graph.invoke({"files": files, "findings": []})
    return result["findings"]
