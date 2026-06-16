"""
Builds a persistent ChromaDB vector index from knowledge_base/*.md.

Run: uv run python -m src.rag.build_index
"""
import glob
import os

import chromadb
from chromadb.utils import embedding_functions
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import settings

KB_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_base")
COLLECTION_NAME = "code_review_kb"


def build_index():
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    client = chromadb.PersistentClient(path=settings.chroma_db_dir)

    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(name=COLLECTION_NAME, embedding_function=embed_fn)

    documents, ids, metadatas = [], [], []
    for path in glob.glob(os.path.join(KB_DIR, "*.md")):
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        source = os.path.basename(path)

        for i, chunk in enumerate(splitter.split_text(text)):
            documents.append(chunk)
            ids.append(f"{source}-{i}")
            metadatas.append({"source": source})

    if not documents:
        raise RuntimeError(f"No markdown files found in {KB_DIR}")

    collection.add(documents=documents, ids=ids, metadatas=metadatas)
    print(f"Indexed {len(documents)} chunks from {KB_DIR} into '{COLLECTION_NAME}'")


if __name__ == "__main__":
    build_index()
