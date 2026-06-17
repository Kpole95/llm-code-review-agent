"""LangGraph pipeline: analyze -> detect -> enrich."""
import re
from concurrent.futures import ThreadPoolExecutor

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

# Run enrichment for findings concurrently. Each worker does fix + explanation
# for one finding; this caps simultaneous API calls to avoid rate limits.
_ENRICH_WORKERS = 5


# --- UI-leak scrubbing ------------------------------------------------------
# The model occasionally bleeds the Streamlit card template into a snippet
# (e.g. </div><div class="code-label">SUGGESTED FIX</div>...). We strip ONLY
# that leaked template, never generic angle brackets — legitimate code like
# List<String> and real XSS snippets (<h1>, <img>) must survive untouched.
_TEMPLATE_BOUNDARY_RE = re.compile(
    r'</div>\s*<div[^>]*class\s*=\s*"(?:code-|finding-)', re.IGNORECASE
)
_UI_CLASS_TAG_RE = re.compile(
    r'</?(?:div|span)[^>]*class\s*=\s*"[^"]*\b'
    r'(?:code-label|code-block|code-fix|code-original|finding-card|finding-header|'
    r'finding-desc|finding-location|finding-category|severity-badge|explanation|file-rule)'
    r'\b[^"]*"[^>]*>',
    re.IGNORECASE,
)
_ORPHAN_CLOSER_RE = re.compile(r'</(?:div|span)>', re.IGNORECASE)


def _scrub_ui_leak(text: str) -> str:
    """Brutally amputate any leaked Streamlit UI templates from the LLM's output."""
    if not text:
        return text
    
    # 1. The Nuclear Option: If it tries to start a new UI section, chop it off.
    cutoff_phrases = [
        '</div><div class="code-label">',
        '</div>\n<div class="code-label">',
        '<div class="code-label">SUGGESTED FIX',
    ]
    
    for phrase in cutoff_phrases:
        if phrase in text:
            # Keep only everything BEFORE the leaked HTML
            text = text.split(phrase)[0]

    # 2. Clean up any trailing orphaned tags that got left behind
    text = text.replace('</div>', '').replace('</span>', '')
    
    return text.strip()


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom < 1e-8:
        return 0.0
    return float(np.dot(a, b) / denom)


def deduplicate_findings(findings, line_tolerance=3, similarity_threshold=0.82):
    """
    Merge duplicates in two passes: an exact match on (file, line, category),
    then a semantic pass that embeds 'category + description' so near-duplicates
    from the regex and LLM detectors (different lines, same issue) collapse.
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

    # Composite key: category anchors same-type findings together, description
    # separates genuinely different issues. Embedded once, outside the loops.
    composite = [f"{f.category} {f.description}" for f in pre_deduped]
    embeddings = np.array(_embed_fn(composite))

    merged = set()
    kept = []
    # ... inside deduplicate_findings ...
    
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
            
            # --- THE FIX: Aggressive Category Short-Circuit ---
            # If the OWASP category is identical and it's within the line tolerance (3 lines),
            # it is 100% the LLM double-reporting. Merge it instantly.
            if f.category == g.category:
                merged.add(j)
                group.append(g)
                continue

            # Fallback: Semantic check ONLY for mismatched categories (e.g. 'error_handling' vs 'null_dereference')
            sim = _cosine_similarity(embeddings[i], embeddings[j])
            if sim > 0.72: # Lowered from 0.82 to be more forgiving
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


def _enrich_one(raw: dict) -> dict:
    """Fully enrich one finding: context -> fix -> explanation, then scrub leaks."""
    finding = BugFinding(**raw)

    if not finding.context_docs:
        finding.context_docs = get_context_for_finding(finding)

    if finding.original_snippet:
        finding.suggested_fix = suggest_fix(finding)
        finding.explanation = explain_finding(finding)

    finding.original_snippet = _scrub_ui_leak(finding.original_snippet)
    finding.suggested_fix = _scrub_ui_leak(finding.suggested_fix)
    finding.explanation = _scrub_ui_leak(finding.explanation)

    return finding.model_dump()


def enrich_node(state: AgentState) -> AgentState:
    """Enrich all findings in parallel (independent per finding)."""
    raws = state["findings"]
    if not raws:
        state["findings"] = []
        return state

    workers = min(_ENRICH_WORKERS, len(raws))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        # .map preserves input order, so findings stay in their original order.
        state["findings"] = list(executor.map(_enrich_one, raws))

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