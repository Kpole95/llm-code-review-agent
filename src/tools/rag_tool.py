"""Builds a retrieval query from a finding and fetches relevant knowledge-base context."""
from src.agent.state import BugFinding
from src.rag.retriever import retrieve_context


def get_context_for_finding(finding: BugFinding, k: int = 2) -> list[str]:
    query = f"{finding.category} {finding.description}"
    return retrieve_context(query, k=k)
