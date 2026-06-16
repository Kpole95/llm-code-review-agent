"""Queries the persisted ChromaDB knowledge base."""
import chromadb
from chromadb.utils import embedding_functions

from src.config import settings
from src.rag.build_index import COLLECTION_NAME

_embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)
_client = chromadb.PersistentClient(path=settings.chroma_db_dir)


def retrieve_context(query: str, k: int = 3) -> list[str]:
    """Return the text of the k most similar chunks for the given query."""
    collection = _client.get_collection(COLLECTION_NAME, embedding_function=_embed_fn)
    results = collection.query(query_texts=[query], n_results=k)
    return results["documents"][0] if results["documents"] else []


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "how to prevent SQL injection"
    for chunk in retrieve_context(q):
        print("---")
        print(chunk)
