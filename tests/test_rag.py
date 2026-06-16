"""
Requires the index to exist — run `uv run python -m src.rag.build_index` first.
"""
from src.rag.retriever import retrieve_context


def test_retrieve_sql_injection_context():
    results = retrieve_context("how to prevent SQL injection in Python", k=3)
    assert results, "Expected at least one result"

    combined = " ".join(results).lower()
    # The retrieved chunks should actually be about SQL/parameterization,
    # not some unrelated section of the KB.
    assert "sql" in combined or "parameteri" in combined