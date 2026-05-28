"""
ChromaDB vector store for memory embeddings.
"""

import os
import chromadb
from chromadb.config import Settings as ChromaSettings
from config.settings import settings


COLLECTION_NAME = "city_town_memories"

_client: chromadb.PersistentClient | None = None
_collection: chromadb.Collection | None = None


def get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        chroma_path = settings.chromadb_path
        if not os.path.isabs(chroma_path):
            chroma_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                chroma_path,
            )
        os.makedirs(chroma_path, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=chroma_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def get_collection() -> chromadb.Collection:
    global _collection
    if _collection is None:
        client = get_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def add_memory(memory_id: str, text: str, embedding: list[float],
               metadata: dict | None = None) -> str:
    """Add a memory embedding to the vector store. Returns the chroma_id."""
    collection = get_collection()
    collection.add(
        ids=[memory_id],
        embeddings=[embedding],
        documents=[text],
        metadatas=[metadata or {}],
    )
    return memory_id


def search_similar(query_embedding: list[float], top_k: int = 5,
                   filter_metadata: dict | None = None) -> list[dict]:
    """Search for similar memories by vector similarity."""
    collection = get_collection()
    where = _build_filter(filter_metadata) if filter_metadata else None
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    out = []
    if results and results["ids"] and results["ids"][0]:
        for i in range(len(results["ids"][0])):
            out.append({
                "id": results["ids"][0][i],
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i],
            })
    return out


def delete_memory(memory_id: str) -> None:
    """Remove a memory from the vector store."""
    collection = get_collection()
    collection.delete(ids=[memory_id])


def _build_filter(metadata: dict) -> dict:
    """Build ChromaDB where clause from metadata dict."""
    if not metadata:
        return None
    conditions = []
    for key, value in metadata.items():
        conditions.append({key: {"$eq": value}})
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}
